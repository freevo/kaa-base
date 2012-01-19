.. module:: kaa.db
   :synopsis: A flexible sqlite-backed object database with support 
              for inverted indexes
.. _db:

Object Database
===============

Write intro and examples.



.. _attrflags:

Attribute Flags
---------------

These flags are used to define object attributes.  See
:meth:`~kaa.db.Database.register_object_type_attrs` for more details.


.. attribute:: kaa.db.ATTR_SIMPLE

   Attribute is persisted with the object, but cannot be used with
   :meth:`~kaa.db.Database.query`.  It can be any Python type that
   is picklable.

   The attribute data is stored inside an internal pickled object and does
   not occupy a dedicated column in the underlying database table for the
   object type.


.. attribute:: kaa.db.ATTR_SEARCHABLE

   Attribute can be used with :meth:`~kaa.db.Database.query`, but the type
   must be one of *int*, *float*, *str*, *unicode*, *buffer*, or *bool*.
   
   The attribute data is stored in a dedicated column in the underlying
   database table.


.. attribute:: kaa.db.ATTR_INDEXED

   If this flag is set, the attribute is indexed for faster queries.

   Internally, an SQL index is placed on the column.  Multiple ATTR_INDEXED
   attributes may be used in a composite index by specifying the *indexes*
   argument with :meth:`~kaa.db.Database.register_object_type_attrs`.


.. attribute:: kaa.db.ATTR_IGNORE_CASE

   Queries on this attribute are case-insensitive, however when the attribute
   is accessed from the :class:`~kaa.db.ObjectRow`, the original case is
   preserved.

   Attributes with this flag require roughly double the space in the database,
   because two copies are kept (one in lower case for searching, and one in the
   original case).


.. attribute:: kaa.db.ATTR_INVERTED_INDEX

   Values for this attribute are parsed into terms and individual terms can
   be searched to find the object.

   When it's registered, the attribute must also be associated with a
   registered inverted index.


.. attribute:: kaa.db.ATTR_INDEXED_IGNORE_CASE

   A bitmap of :attr:`~kaa.db.ATTR_INDEXED` and
   :attr:`~kaa.db.ATTR_IGNORE_CASE`.  Provided for convenience and code
   readability.


Classes
-------

.. kaaclass:: kaa.db.Database
   :synopsis:

   .. automethods::
   .. autoproperties::
   .. autosignals::



.. class:: ObjectRow

   ObjectRow objects represent a single object from a :class:`kaa.db.Database`,
   and are returned by, or may be passed to, many Database methods.

   For the most part, ObjectRows behave like a read-only dict, providing most
   (though not all) of the common dict methods, however ObjectRow is a custom
   type written in C for performance.



.. kaaclass:: kaa.db.QExpr
