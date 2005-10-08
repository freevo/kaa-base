import string, os, time, re, math, cPickle
from kaa.base.utils import str_to_unicode
from sets import Set
from pysqlite2 import dbapi2 as sqlite

__all__ = ['Database', 'QExpr', 'ATTR_SIMPLE', 'ATTR_SEARCHABLE', 
           'ATTR_INDEXED', 'ATTR_KEYWORDS', 'ATTR_KEYWORDS_FILENAME']

CREATE_SCHEMA = """
    CREATE TABLE meta (
        attr        TEXT UNIQUE, 
        value       TEXT
    );
    INSERT INTO meta VALUES('keywords_filecount', 0);
    INSERT INTO meta VALUES('version', 0.1);

    CREATE TABLE types (
        id              INTEGER PRIMARY KEY AUTOINCREMENT, 
        name            TEXT UNIQUE,
        attrs_pickle    BLOB
    );

    CREATE TABLE words (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        word            TEXT,
        count           INTEGER
    );
    CREATE UNIQUE INDEX words_idx on WORDS (word) ON CONFLICT REPLACE;

    CREATE TABLE words_map (
        rank            INTEGER,
        word_id         INTEGER,
        object_type     INTEGER,
        object_id       INTEGER,
        frequency       FLOAT
    );
    CREATE INDEX words_map_word_idx ON words_map (word_id, rank, object_type);
    CREATE INDEX words_map_object_idx ON words_map (object_type, object_id);
"""


ATTR_SIMPLE            = 0x00
ATTR_SEARCHABLE        = 0x01      # Is a SQL column, not a pickled field
ATTR_INDEXED           = 0x02      # Will have an SQL index
ATTR_KEYWORDS          = 0x04      # Also indexed for keyword queries

ATTR_KEYWORDS_FILENAME = 0x100     # Treat as filename for keywords index

STOP_WORDS = (
    "about", "and", "are", "but", "com", "for", "from", "how", "not", 
    "some", "that", "the", "this", "was", "what", "when", "where", "who", 
    "will", "with", "the", "www", "http", "org", "of"
)
WORDS_DELIM = re.compile("[\W_]+", re.U)

# Word length limits for keyword indexing
MIN_WORD_LENGTH = 2
MAX_WORD_LENGTH = 30

# These are special attributes for querying.  Attributes with
# these names cannot be registered.
RESERVED_ATTRIBUTES = ("parent", "object", "keywords", "type", "limit",
                       "attrs", "distinct")


def _value_to_printable(value):
    """
    Takes a list of mixed types and outputs a unicode string.  For
    example, a list [42, 'foo', None, "foo's string"], this returns the
    string:

        (42, 'foo', NULL, 'foo''s string')

    Single quotes are escaped as ''.  This is suitable for use in SQL 
    queries.  
    """
    if type(value) in (int, long, float):
        return str(value)
    elif value == None:
        return "NULL"
    elif type(value) == unicode:
        return "'%s'" % value.replace("'", "''")
    elif type(value) == str:
        return "'%s'" % str_to_unicode(value.replace("'", "''"))
    elif type(value) in (list, tuple):
        fixed_items = []
        for item in value:
            fixed_items.append(_value_to_printable(item))
        return '(' + ','.join(fixed_items) + ')'
    else:
        raise Exception, "Unsupported type '%s' given to _value_to_printable" % type(value)



class QExpr(object):
    """
    Flexible query expressions for use with Database.query()
    """
    def __init__(self, operator, operand):
        assert(operator in ("=", "!=", "<", "<=", ">", ">=", "in", "not in",
                            "range"))
        if operator in ("in", "not in", "range"):
            assert(type(operand) == tuple)
            if operator == "range":
                assert(len(operand) == 2)

        self._operator = operator
        self._operand = operand

    def as_sql(self, var):
        if self._operator == "range":
            a, b = self._operand
            return "%s >= ? AND %s < ?" % (var, var), \
                   (_value_to_printable(a), _value_to_printable(b))
        else:
            return "%s %s ?" % (var, self._operator.upper()), \
                   (_value_to_printable(self._operand),)


class Database:
    def __init__(self, dbfile = None):
        if not dbfile:
            dbfile = "kaavfs.sqlite"

        self._object_types = {}
        self._dbfile = dbfile
        self._open_db()


    def __del__(self):
        self.commit()


    def _open_db(self):
        self._db = sqlite.connect(self._dbfile)
        self._cursor = self._db.cursor()
        self._cursor.execute("PRAGMA synchronous=OFF")
        self._cursor.execute("PRAGMA count_changes=OFF")
        self._cursor.execute("PRAGMA cache_size=50000")

        if not self.check_table_exists("meta"):
            self._db.close()
            self._create_db()

        self._load_object_types()


    def _db_query(self, statement, args = ()):
        self._cursor.execute(statement, args)
        rows = self._cursor.fetchall()
        return rows


    def _db_query_row(self, statement, args = ()):
        rows = self._db_query(statement, args)
        if len(rows) == 0:
            return None
        return rows[0]


    def check_table_exists(self, table):
        res = self._db_query_row("SELECT name FROM sqlite_master where " \
                                 "name=? and type='table'", (table,))
        return res != None


    def _create_db(self):
        try:
            os.unlink(self._dbfile)
        except:
            pass
        f = os.popen("sqlite3 %s" % self._dbfile, "w")
        f.write(CREATE_SCHEMA)
        f.close()
        self._open_db()

        self.register_object_type_attrs("dir")


    def register_object_type_attrs(self, type_name, attr_list = ()):
        if type_name in self._object_types:
            # This type already exists.  Compare given attributes with
            # existing attributes for this type.
            cur_type_id, cur_type_attrs = self._object_types[type_name]
            new_attrs = {}
            db_needs_update = False
            for name, type, flags in attr_list:
                if name not in cur_type_attrs:
                    new_attrs[name] = type, flags
                    if flags:
                        # New attribute isn't simple, needs to alter table.
                        db_needs_update = True

            if len(new_attrs) == 0:
                # All these attributes are already registered; nothing to do.
                return

            if not db_needs_update:
                # Only simple (i.e. pickled only) attributes are added, so we
                # don't need to alter the table, just update the types table.
                cur_type_attrs.update(new_attrs)
                self._db_query("UPDATE types SET attrs_pickle=? WHERE id=?",
                           (buffer(cPickle.dumps(cur_type_attrs, 2)), cur_type_id))
                return

            # Update the attr list to merge both existing and new attributes.
            # We need to update the database now.
            attr_list = []
            for name, (type, flags) in cur_type_attrs.items() + new_attrs.items():
                attr_list.append((name, type, flags))

        else:
            new_attrs = {}
            cur_type_id = None
            # Merge standard attributes with user attributes for this type.
            attr_list = (
                ("id", int, ATTR_SEARCHABLE),
                ("parent_type", int, ATTR_SEARCHABLE),
                ("parent_id", int, ATTR_SEARCHABLE),
                ("pickle", buffer, ATTR_SEARCHABLE),
            ) + tuple(attr_list)

        table_name = "objects_%s" % type_name

        create_stmt = "CREATE TABLE %s_tmp ("% table_name

        # Iterate through type attributes and append to SQL create statement.
        attrs = {}
        for name, type, flags in attr_list:
            assert(name not in RESERVED_ATTRIBUTES)
            # If flags is non-zero it means this attribute needs to be a
            # column in the table, not a pickled value.
            if flags:
                sql_types = {int: "INTEGER", float: "FLOAT", buffer: "BLOB", 
                             unicode: "TEXT", str: "BLOB"}
                if type not in sql_types:
                    raise ValueError, "Type '%s' not supported" % str(type)
                create_stmt += "%s %s" % (name, sql_types[type])
                if name == "id":
                    # Special case, these are auto-incrementing primary keys
                    create_stmt += " PRIMARY KEY AUTOINCREMENT"
                create_stmt += ","

            attrs[name] = (type, flags)

        create_stmt = create_stmt.rstrip(",") + ")"
        self._db_query(create_stmt)

        # Add this type to the types table, including the attributes
        # dictionary.
        self._db_query("INSERT OR REPLACE INTO types VALUES(?, ?, ?)", 
                       (cur_type_id, type_name, buffer(cPickle.dumps(attrs, 2))))

        if new_attrs:
            # Migrate rows from old table to new one.
            columns = filter(lambda x: cur_type_attrs[x][1], cur_type_attrs.keys())
            columns = string.join(columns, ",")
            self._db_query("INSERT INTO %s_tmp (%s) SELECT %s FROM %s" % \
                           (table_name, columns, columns, table_name))

            # Delete old table.
            self._db_query("DROP TABLE %s" % table_name)

        # Rename temporary table.
        self._db_query("ALTER TABLE %s_tmp RENAME TO %s" % \
                       (table_name, table_name))


        # Create index for locating all objects under a given parent.
        self._db_query("CREATE INDEX %s_parent_idx on %s (parent_id, "\
                       "parent_type)" % (table_name, table_name))

        # If any of these attributes need to be indexed, create the index
        # for that column.  TODO: need to support indexes on multiple
        # columns.
        for name, type, flags in attr_list:
            if flags & ATTR_INDEXED:
                self._db_query("CREATE INDEX %s_%s_idx ON %s (%s)" % \
                               (table_name, name, table_name, name))

        self._load_object_types()


    def _load_object_types(self):
        for id, name, attrs in self._db_query("SELECT * from types"):
            self._object_types[name] = id, cPickle.loads(str(attrs))
    

    def _make_query_from_attrs(self, query_type, attrs, type_name):
        type_attrs = self._object_types[type_name][1]

        columns = []
        values = []
        placeholders = []

        for key in attrs.keys():
            if attrs[key] == None:
                del attrs[key]
        attrs_copy = attrs.copy()
        for name, (attr_type, flags) in type_attrs.items():
            if flags != ATTR_SIMPLE and name in attrs:
                columns.append(name)
                placeholders.append("?")
                if name in attrs:
                    value = attrs[name]
                    # Coercion for numberic types
                    if type(value) in (int, long, float) and attr_type in (int, long, float):
                        value = attr_type(value)

                    if attr_type != type(value):
                        raise ValueError, "Type mismatch in query for %s: '%s' (%s) is not a %s" % \
                                          (name, str(value), str(type(value)), str(attr_type))
                    if attr_type == str:
                        # Treat strings (non-unicode) as buffers.
                        value = buffer(value)
                    values.append(value)
                    del attrs_copy[name]
                else:
                    values.append(None)

        if len(attrs_copy) > 0:
            columns.append("pickle")
            values.append(buffer(cPickle.dumps(attrs_copy, 2)))
            placeholders.append("?")

        table_name = "objects_" + type_name

        if query_type == "add":
            columns = string.join(columns, ",")
            placeholders = string.join(placeholders, ",")
            q = "INSERT INTO %s (%s) VALUES(%s)" % (table_name, columns, placeholders)
        else:
            q = "UPDATE %s SET " % table_name
            for col, ph in zip(columns, placeholders):
                q += "%s=%s," % (col, ph)
            # Trim off last comma
            q = q.rstrip(",")
            q += " WHERE id=?"
            values.append(attrs["id"])

        return q, values
    

    def delete_object(self, (object_type, object_id)):
        """
        Deletes the specified object.
        """
        # TODO: recursively delete all children of this object.
        self._delete_object_keywords((object_type, object_id))
        self._db_query("DELETE FROM objects_%s WHERE id=?" % \
                       object_type, (object_id,))
        

    def add_object(self, object_type, parent = None, **attrs):
        """
        Adds an object of type 'object_type' to the database.  Parent is a
        (type, id) tuple which refers to the object's parent.  'object_type'
        and 'type' is a type name as given to register_object_type_attrs().
        attrs kwargs will vary based on object type.  ATTR_SIMPLE attributes
        which a None are not added.

        This method returns the dict that would be returned if this object
        were queried by query_normalized().  The "id" key of this dict refers
        to the id number assigned to this object.
        """
        type_attrs = self._object_types[object_type][1]
        if parent:
            attrs["parent_type"] = self._object_types[parent[0]][0]
            attrs["parent_id"] = parent[1]
        #attrs["name"] = object_name
        query, values = self._make_query_from_attrs("add", attrs, object_type)
        self._db_query(query, values)

        # Add id given by db, as well as object type.
        attrs["id"] = self._cursor.lastrowid
        attrs["type"] = object_type

        # Index keyword attributes
        word_parts = []
        for name, (attr_type, flags) in type_attrs.items():
            if name in attrs and flags & ATTR_KEYWORDS:
                word_parts.append((attrs[name], 1.0, attr_type, flags))
        words = self._score_words(word_parts)
        self._add_object_keywords((object_type, attrs["id"]), words)

        # For attributes which aren't specified in kwargs, add them to the
        # dict we're about to return, setting default value to None.
        for name, (attr_type, flags) in type_attrs.items():
            if name not in attrs:
                attrs[name] = None

        return attrs


    def update_object(self, (object_type, object_id), parent = None, **attrs):
        """
        Update an object in the database.  For updating, object is identified
        by a (type, id) tuple.  Parent is a (type, id) tuple which refers to
        the object's parent.  If specified, the object is reparented,
        otherwise the parent remains the same as when it was added with
        add_object().  attrs kwargs will vary based on object type.  If a
        ATTR_SIMPLE attribute is set to None, it will be removed from the
        pickled dictionary.
        """
        type_attrs = self._object_types[object_type][1]
        needs_keyword_reindex = False
        keyword_columns = []
        for name, (attr_type, flags) in type_attrs.items():
            if flags & ATTR_KEYWORDS:
                if name in attrs:
                    needs_keyword_reindex = True
                keyword_columns.append(name)

        q = "SELECT pickle%%s FROM objects_%s WHERE id=?" % object_type
        if needs_keyword_reindex:
            q %= "," + ",".join(keyword_columns)
        else:
            q %= ""
        
        row = self._db_query_row(q, (object_id,))
        assert(row)
        if row[0]:
            row_attrs = cPickle.loads(str(row[0]))
            row_attrs.update(attrs)
            attrs = row_attrs
        if parent:
            attrs["parent_type"] = self._object_types[parent[0]][0]
            attrs["parent_id"] = parent[1]
        attrs["id"] = object_id
        query, values = self._make_query_from_attrs("update", attrs, object_type)
        self._db_query(query, values)

        if needs_keyword_reindex:
            # We've modified a ATTR_KEYWORD column, so we need to reindex all
            # all keyword attributes for this row.

            # Merge the other keyword columns into attrs dict.
            for n, name in zip(range(len(keyword_columns)), keyword_columns):
                if name not in attrs:
                    attrs[name] = row[n + 1]

            # Remove existing indexed words for this object.
            self._delete_object_keywords((object_type, object_id))

            # Re-index 
            word_parts = []
            for name, (attr_type, flags) in type_attrs.items():
                if flags & ATTR_KEYWORDS:
                    if attr_type == str and type(attrs[name]) == buffer:
                        # _score_words wants only string or unicode values.
                        attrs[name] = str(attrs[name])
                    word_parts.append((attrs[name], 1.0, attr_type, flags))
            words = self._score_words(word_parts)
            self._add_object_keywords((object_type, object_id), words)


    def commit(self):
        self._db.commit()


    def query(self, **attrs):
        """
        Query the database for objects matching all of the given attributes
        (specified in kwargs).  There are a few special kwarg attributes:

             parent: (type, id) tuple referring to the object's parent, where
                     type is the name of the type.
             object: (type, id) tuple referring to the object itself.
           keywords: a string of search terms for keyword search.
               type: only search items of this type (e.g. "images"); if None
                     (or not specified) all types are searched.
              limit: return only this number of results; if None (or not 
                     specified) all matches are returned.  For better
                     performance it is highly recommended a limit is specified
                     for keyword searches.
              attrs: A list of attributes to be returned.  If not specified,
                     all possible attributes.
           distinct: If True, selects only distinct rows.  When distinct is
                     specified, attrs kwarg must also be given, and no
                     specified attrs can be ATTR_SIMPLE.

        Return value is a tuple (columns, results), where columns is a 
        dictionary that maps object types to a tuple of column names, and
        results is a list of rows that satisfy the query where each item
        in each row corresponds to the item in the column tuple for that
        type.  The first item in each results row is the name of the type,
        so for a given row, you can get the column names by columns[row[0]].

        This "raw" tuple can be passed to normalize_query_results() which will
        return a list of dicts for more convenient use.
        """
        query_info = {}

        if "object" in attrs:
            attrs["type"], attrs["id"] = attrs["object"]
            del attrs["object"]

        if "keywords" in attrs:
            # TODO: Possible optimization: do keyword search after the query
            # below only on types that have results iff all queried columns are
            # indexed.

            # If search criteria other than keywords are specified, we can't
            # enforce a limit on the keyword search, otherwise we might miss
            # intersections.
            if len(Set(attrs).difference(("type", "limit", "keywords"))) > 0:
                limit = None 
            else: 
                limit = attrs.get("limit") 
            kw_results = self._query_keywords(attrs["keywords"], limit, 
                                              attrs.get("type"))

            # No matches to our keyword search, so we're done.
            if not kw_results:
                return {}, []

            kw_results_by_type = {}
            for tp, id in kw_results:
                if tp not in kw_results_by_type:
                    kw_results_by_type[tp] = []
                kw_results_by_type[tp].append(id)

            del attrs["keywords"]
        else:
            kw_results = kw_results_by_type = None


        if "type" in attrs:
            type_list = [(attrs["type"], self._object_types[attrs["type"]])]
            del attrs["type"]
        else:
            type_list = self._object_types.items()

        if "parent" in attrs:
            parent_type, parent_id = attrs["parent"]
            attrs["parent_type"] = self._object_types[parent_type][0]
            attrs["parent_id"] = parent_id
            del attrs["parent"]

        if "limit" in attrs:
            result_limit = attrs["limit"]
            del attrs["limit"]
        else:
            result_limit = None

        if "attrs" in attrs:
            requested_columns = attrs["attrs"]
            del attrs["attrs"]
        else:
            requested_columns = None

        query_type = "ALL"
        if "distinct" in attrs:
            if attrs["distinct"]:
                if not requested_columns:
                    raise ValueError, "Distinct query specified, but no attrs kwarg given."
                query_type = "DISTINCT"
            del attrs["distinct"]


        results = []
        query_info["columns"] = {}
        for type_name, (type_id, type_attrs) in type_list:
            if kw_results and type_id not in kw_results_by_type:
                # If we've done a keyword search, don't bother querying 
                # object types for which there were no keyword hits.
                continue

            # List of attribute dicts for this type.
            if requested_columns:
                columns = requested_columns
                # Ensure that all the requested columns exist for this type
                missing = tuple(Set(columns).difference(type_attrs.keys()))
                if missing:
                    raise ValueError, "One or more requested attributes %s are not available for type '%s'" % \
                                      (str(missing), type_name)
                # Ensure that no requested attrs are ATTR_SIMPLE
                simple = [ x for x in columns if type_attrs[x][1] == ATTR_SIMPLE ]
                if simple:
                    raise ValueError, "ATTR_SIMPLE attributes cannot yet be specified in attrs kwarg %s" % \
                                      str(tuple(simple))
            else:
                # Select only sql columns (i.e. attrs that aren't ATTR_SIMPLE)
                columns = filter(lambda x: type_attrs[x][1] != ATTR_SIMPLE, type_attrs.keys())

            # Construct a query based on the supplied attributes for this
            # object type.  If any of the attribute names aren't valid for
            # this type, then we don't bother matching, since this an AND
            # query and there aren't be any matches.
            if len(Set(attrs).difference(columns)) > 0:
                continue

            q = "SELECT %s '%s'%%s,%s FROM objects_%s" % \
                (query_type, type_name, string.join(columns, ","), type_name)

            if kw_results != None:
                q %= ",%d+id as computed_id" % (type_id * 10000000)
                q +=" WHERE id IN %s" % _value_to_printable(kw_results_by_type[type_id])
            else:
                q %= ""

            query_values = []
            for attr, value in attrs.items():
                attr_type = type_attrs[attr][0]
                if type(value) != QExpr:
                    value = QExpr("=", value)

                if type(value._operand) in (int, long, float) and attr_type in (int, long, float):
                    value._operand = attr_type(value._operand)
                if value._operator not in ("range", "in", "not in") and \
                   type(value._operand) != attr_type:
                    raise ValueError, "Type mismatch in query: '%s' (%s) is not a %s" % \
                                          (str(value._operand), str(type(value._operand)), str(attr_type))
                if type(value._operand) == str:
                    # Treat strings (non-unicode) as buffers.
                    value._operand = buffer(value._operand)

                if q.find("WHERE") == -1:
                    q += " WHERE "
                else:
                    q += " AND "

                sql, values = value.as_sql(attr)
                q += sql
                query_values.extend(values)
            
            if result_limit != None:
                q += " LIMIT %d" % result_limit

            rows = self._db_query(q, query_values)
            results.extend(rows)
            if kw_results:
                query_info["columns"][type_name] = ["type", "computed_id"] + columns
            else:
                query_info["columns"][type_name] = ["type"] + columns

        # If keyword search was done, sort results to preserve order given in 
        # kw_results.
        if kw_results:
            # Convert (type,id) tuple to computed id value.
            kw_results = map(lambda (type, id): type*10000000+id, kw_results)
            # Create a dict mapping each computed id value to its position.
            kw_results_order = dict(zip(kw_results, range(len(kw_results))))
            # Now sort based on the order dict.  The second item in each row
            # will be the computed id for that row.
            results.sort(lambda a, b: cmp(kw_results_order[a[1]], kw_results_order[b[1]]))

        return query_info, results


    def query_normalized(self, **attrs):
        """
        Performs a query as in query() and returns normalized results.
        """
        return self.normalize_query_results(self.query(**attrs))


    def normalize_query_results(self, (query_info, results)):
        """
        Takes a results tuple as returned from query() and converts to a list
        of dicts.  Each result dict is given a "type" entry which corresponds 
        to the type name of that object.  This function also unpickles the
        pickle contained in the row, and creates a "parent" key that holds
        (parent type name, parent id).
        """
        if len(results) == 0:
            return []

        new_results = []
        # Map object type ids to names.
        object_type_ids = dict( [(b[0],a) for a,b in self._object_types.items()] )
        # For type converstion, currently just used for converting buffer 
        # values to strings.
        type_maps = {}
        for type_name, (type_id, type_attrs) in self._object_types.items():
            col_desc = query_info["columns"].get(type_name)
            if col_desc:
                type_maps[type_name] = [ (x, str) for x in type_attrs 
                                         if type_attrs[x][0] == str and 
                                            x in col_desc 
                                       ]

        for row in results:
            col_desc = query_info["columns"][row[0]]
            result = dict(zip(col_desc, row))
            for attr, tp in type_maps[row[0]]:
                result[attr] = tp(result[attr])

            if result.get("pickle"):
                pickle = cPickle.loads(str(result["pickle"]))
                del result["pickle"]
                result.update(pickle)

            # Add convenience parent key, mapping parent_type id to name.
            if result.get("parent_type"):
                result["parent"] = (object_type_ids.get(result["parent_type"]), 
                                    result["parent_id"])
            new_results.append(result)
        return new_results


    def list_query_results_names(self, (query_info, results)):
        """
        Do a quick-and-dirty list of filenames given a query results list,
        sorted by filename.
        """
        return []
        # XXX: This logic needs to be in vfs, not db.
        #name_index = {}
        #for type, c in query_info["columns"].items():
        #    name_index[type] = c.index("name")
        #files = [ str(row[name_index[row[0]]]) for row in results ]
        #files.sort()
        #return files


    def _score_words(self, text_parts):
        """
        Scores the words given in text_parts, which is a list of tuples
        (text, coeff, type), where text is the string of words
        to be scored, coeff is the weight to give each word in this part
        (1.0 is normal), and type is one of ATTR_KEYWORDS_*.  Text parts are
        either unicode objects or strings.  If they are strings, they are
        given to str_to_unicode() to try to decode them intelligently.

        Each word W is given the score:
             sqrt( (W coeff * W count) / total word count )

        Counts are relative to the given object, not all objects in the
        database.
        
        Returns a dict of words whose values hold the score caclulated as
        above.
        """
        words = {}
        total_words = 0

        for text, coeff, attr_type, flags in text_parts:
            if not text:
                continue
            if type(text) not in (unicode, str):
                raise ValueError, "Invalid type (%s) for ATTR_KEYWORDS attribute.  Only unicode or str allowed." % \
                                  str(type(text)) 
            if attr_type == str:
                text = str_to_unicode(text)

            if flags & ATTR_KEYWORDS_FILENAME:
                dirname, filename = os.path.split(text)
                fname_noext, ext = os.path.splitext(filename)
                # Remove the first 2 levels (like /home/user/) and then take
                # the last two levels that are left.
                levels = dirname.strip('/').split(os.path.sep)[2:][-2:] + [fname_noext]
                parsed = WORDS_DELIM.split(string.join(levels)) + [fname_noext]
            else:
                parsed = WORDS_DELIM.split(text)

            for word in parsed:
                if not word or len(word) > MAX_WORD_LENGTH:
                    # Probably not a word.
                    continue
                word = word.lower()

                if len(word) < MIN_WORD_LENGTH or word in STOP_WORDS:
                    continue
                if word not in words:
                    words[word] = coeff
                else:
                    words[word] += coeff
                total_words += 1

        # Score based on word frequency in document.  (Add weight for 
        # non-dictionary words?  Or longer words?)
        for word, score in words.items():
            words[word] = math.sqrt(words[word] / total_words)
        return words


    def _delete_object_keywords(self, (object_type, object_id)):
        """
        Removes all indexed keywords for the given object.  This function
        must be called when an object is removed from the database, or when
        an object is being updated (and therefore its keywords must be
        re-indexed).
        """
        # Resolve object type name to id
        object_type = self._object_types[object_type][0]

        self._db_query("UPDATE words SET count=count-1 WHERE id IN " \
                       "(SELECT word_id FROM words_map WHERE object_type=? AND object_id=?)",
                       (object_type, object_id))
        self._db_query("DELETE FROM words_map WHERE object_type=? AND object_id=?",
                       (object_type, object_id))

        # FIXME: We need to do this eventually, but there's no index on count,
        # so this could potentially be slow.  It doesn't hurt to leave rows
        # with count=0, so this could be done intermittently.
        #self._db_query("DELETE FROM words WHERE count=0")

        if self._cursor.rowcount > 0:
            self._db_query("UPDATE meta SET value=value-1 WHERE attr='keywords_filecount'")


    def _add_object_keywords(self, (object_type, object_id), words):
        """
        Adds the dictionary of words (as computed by _score_words()) to the
        database for the given object.
        """
        # Resolve object type name to id
        object_type = self._object_types[object_type][0]

        # Holds any of the given words that already exist in the database
        # with their id and count.
        db_words_count = {}

        words_list = _value_to_printable(words.keys())
        q = "SELECT id,word,count FROM words WHERE word IN %s" % words_list
        rows = self._db_query(q)
        for row in rows:
            db_words_count[row[1]] = row[0], row[2]

        # For executemany queries later.
        update_list, map_list = [], []

        for word, score in words.items():
            if word not in db_words_count:
                # New word, so insert it now.
                self._db_query("INSERT INTO words VALUES(NULL, ?, 1)", (word,))
                db_id, db_count = self._cursor.lastrowid, 1
                db_words_count[word] = db_id, db_count
            else:
                db_id, db_count = db_words_count[word]
                update_list.append((db_count + 1, db_id))

            map_list.append((int(score*10), db_id, object_type, object_id, score))

        self._cursor.executemany("UPDATE words SET count=? WHERE id=?", update_list)
        self._cursor.executemany("INSERT INTO words_map VALUES(?, ?, ?, ?, ?)", map_list)
        self._db_query("UPDATE meta SET value=value+1 WHERE attr='keywords_filecount'")


    def _query_keywords(self, words, limit = 100, object_type = None):
        """
        Queries the database for the keywords supplied in the words strings.
        (Search terms are delimited by spaces.)  

        The search algorithm tries to optimize for the common case.  When
        words are scored (_score_words()), each word is assigned a score that
        is stored in the database (as a float) and also as an integer in the
        range 0-10, called rank.  (So a word with score 0.35 has a rank 3.)

        Multiple passes are made over the words_map table, first starting at
        the highest rank fetching a certain number of rows, and progressively 
        drilling down to lower ranks, trying to find enough results to fill our
        limit that intersects on all supplied words.  If our limit isn't met
        and all ranks have been searched but there are still more possible 
        matches (because we use LIMIT on the SQL statement), we expand the
        LIMIT (currently by an order of 10) and try again, specifying an 
        OFFSET in the query.

        The worst case scenario is given two search terms, each term matches
        50% of all rows but there is only one intersection row.  (Or, more
        generally, given N rows, each term matches (1/N)*100 percent rows with
        only 1 row intersection between all N terms.)   This could be improved
        by avoiding the OFFSET/LIMIT technique as described above, but that
        approach provides a big performance win in more common cases.  This
        case can be mitigated by caching common word combinations, but it is 
        an extremely difficult problem to solve.

        object_type specifies an type name to search (for example we can
        search type "image" with keywords "2005 vacation"), or if object_type
        is None (default), then all types are searched.

        This function returns a list of (object_type, object_id) tuples 
        which match the query.  The list is sorted by score (with the 
        highest score first).
        """
        t0=time.time()
        # Fetch number of files that are keyword indexed.  (Used in score
        # calculations.)
        row = self._db_query_row("SELECT value FROM meta WHERE attr='keywords_filecount'")
        filecount = int(row[0])

        # Convert words string to a tuple of lower case words.
        words = tuple(str_to_unicode(words).lower().split())
        # Remove words that aren't indexed (words less than MIN_WORD_LENGTH 
        # characters, or and words in the stop list).
        words = filter(lambda x: len(x) >= MIN_WORD_LENGTH and x not in STOP_WORDS, words)
        words_list = _value_to_printable(words)
        nwords = len(words)

        if nwords == 0:
            return []

        # Find word ids and order by least popular to most popular.
        rows = self._db_query("SELECT id,word,count FROM words WHERE word IN %s ORDER BY count" % words_list)
        save = map(lambda x: x.lower(), words)
        words = {}
        ids = []
        for row in rows:
            # Give words weight according to their order
            order_weight = 1 + len(save) - list(save).index(row[1])
            words[row[0]] = {
                "word": row[1],
                "count": row[2],
                "idf_t": math.log(filecount / row[2] + 1) + order_weight
            }
            ids.append(row[0])
            print "WORD: %s (%d), freq=%d/%d, idf_t=%f" % (row[1], row[0], row[2], filecount, words[row[0]]["idf_t"])

        # Not all the words we requested are in the database, so we return
        # 0 results.
        if len(ids) < nwords:
            return []

        if object_type:
            # Resolve object type name to id
            object_type = self._object_types[object_type][0]

        results, state = {}, {}
        for id in ids:
            results[id] = {}
            state[id] = {
                "offset": [0]*11,
                "more": [True]*11
            }

        all_results = {}
        if limit == None:
            limit = filecount

        sql_limit = max(limit*3, 100)
        finished = False
        nqueries = 0

        while not finished:
            for rank in range(10, -1, -1):
                for id in ids:
                    if not state[id]["more"][rank]:
                        continue

                    q = "SELECT object_type,object_id,frequency FROM " \
                        "words_map WHERE word_id=? AND rank=? %s " \
                        "LIMIT ? OFFSET ?"
                    if object_type == None:
                        q %= ""
                        v = (id, rank, sql_limit, state[id]["offset"][rank])
                    else:
                        q %= "AND object_type=?"
                        v = (id, rank, object_type, sql_limit, state[id]["offset"][rank])

                    rows = self._db_query(q, v)
                    nqueries += 1
                    state[id]["more"][rank] = len(rows) == sql_limit

                    for row in rows:
                        results[id][row[0], row[1]] = row[2] * words[id]["idf_t"]

                # end loop over words
                for r in reduce(lambda a, b: Set(a).intersection(Set(b)), results.values()):
                    all_results[r] = 0
                    for id in ids:
                        if r in results[id]:
                            all_results[r] += results[id][r]

                # If we have enough results already, no sense in querying the
                # next rank.
                if limit > 0 and len(all_results) > limit*2:
                    finished = True
                    #print "Breaking at rank:", rank
                    break

            # end loop over ranks
            if finished:
                break

            finished = True
            for index in range(len(ids)):
                id = ids[index]

                if index > 0:
                    last_id = ids[index-1]
                    a = results[last_id]
                    b = results[id]
                    intersect = Set(a).intersection(b)

                    if len(intersect) == 0:
                        # Is there any more at any rank?
                        a_more = b_more = False
                        for rank in range(11):
                            a_more = a_more or state[last_id]["more"][rank]
                            b_more = b_more or state[id]["more"][rank]

                        if not a_more and not b_more:
                            # There's no intersection between these two search
                            # terms and neither have more at any rank, so we 
                            # can stop the whole query.
                            finished = True
                            break

                # There's still hope of a match.  Go through this term and
                # see if more exists at any rank, increasing offset and
                # unsetting finished flag so we iterate again.
                for rank in range(10, -1, -1):
                    if state[id]["more"][rank]:
                        state[id]["offset"][rank] += sql_limit
                        finished = False

            # If we haven't found enough results after this pass, grow our
            # limit so that we expand our search scope.  (XXX: this value may
            # need empirical tweaking.)
            sql_limit *= 10

        # end loop while not finished
        keys = all_results.keys()
        keys.sort(lambda a, b: cmp(all_results[b], all_results[a]))
        if limit > 0:
            keys = keys[:limit]

        #print "* Did %d subqueries" % (nqueries), time.time()-t0, len(keys)
        return keys
        #return [ (all_results[file], file) for file in keys ]
        
