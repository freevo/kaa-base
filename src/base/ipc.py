#
# TODO: document me!
#
# Simple usage example:
#   On server:
#       class Foo:
#           def bar(self):
#               return 42, self
#       foo = Foo()
#       ipc = IPCServer("ipc.socket")
#       ipc.register_object(foo, "foo")
#
#   On client:
#       ipc = IPCClient("ipc.socket")
#       foo = ipc.get_object("foo")
#       print foo.bar()

import socket, os, select, time, types, struct, cPickle, thread, sys
import traceback, string, copy_reg
from new import classobj
import kaa.notifier

DEBUG=2
DEBUG=0

def _debug(level, text, *args):
    if DEBUG  >= level:
        for arg in args:
            text += " " + str(arg)
        print text

def excepthook (type, value, tb):
    if hasattr(type, "_ipc_remote_tb"):
        print "--- An exception has occured remotely.  Here is the remote stack trace:"
        print type._ipc_remote_tb
        print "--- END remote stack trace.\n--- Begin local stack trace:"
    traceback.print_tb(tb)
    print type, value

sys.excepthook = excepthook

def _pickle_slice(slice):
    return _unpickle_slice, (slice.start, slice.stop, slice.step)
def _unpickle_slice(start, stop, step):
    return slice(start, stop, step)
copy_reg.pickle(slice, _pickle_slice, _unpickle_slice)

def get_proxy_type(name):
    clsname = "IPCProxy_" + name
    mod = sys.modules[__name__]
    if hasattr(mod, clsname):
        cls = getattr(mod, clsname)
    else:
        cls = classobj(clsname, (IPCProxy,), {})
        copy_reg.pickle(cls, _pickle_proxy, _unpickle_proxy)
        setattr(mod, clsname, cls)
    return cls

def _pickle_proxy(o):
    basename = o.__class__.__name__.replace("IPCProxy_", "")
    return _unpickle_proxy, (basename, o._ipc_obj, o._ipc_callable, 
                             o._ipc_cache_special_attrs, o._ipc_orig_type)

def _unpickle_proxy(clsname, *args):
    cls = get_proxy_type(clsname)
    for (attr, ismeth) in args[2].items():
        if not ismeth:
            continue
        # FIXME: this list is probably not comprehensive.
        if attr.strip("__") in ("add", "contains", "delitem", "eq", "ge", "getitem", "gt", 
                                "hash", "iadd", "imul", "iter", "le", "len",
                                "lt", "mul", "ne", "nonzero", "rmul", "setitem") or \
           attr in ("next,"):
            #print "--setattr", attr
            setattr(cls, attr, eval("lambda self, *a: self._ipc_meth('%s', a)" % attr))

    i = cls()
    i._ipc_obj, i._ipc_callable, i._ipc_cache_special_attrs, i._ipc_orig_type = args
    if i._ipc_orig_type and i._ipc_orig_type[0] == "\x01":
        i._ipc_class = types.__dict__[i._ipc_orig_type[1:]]
    else:
        try:
            i._ipc_class = cPickle.loads(i._ipc_orig_type)
        except:
            i._ipc_class = None
    return i


def isproxy(obj):
    # Not foolproof, but good enough for me.
    return hasattr(obj, "_ipc_obj")


class IPCDisconnectedError(Exception):
    pass

class IPCTimeoutError(Exception):
    pass

class IPCServer:

    def __init__(self, address):
        if type(address) in types.StringTypes:
            if os.path.exists(address):
                os.unlink(address)
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        elif type(address) == tuple:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket.setblocking(False)
        self.socket.bind(address)
        self.socket.listen(5)
        monitor = kaa.notifier.SocketDispatcher(self.handle_connection)
        monitor.register(self.socket)
        
        self.clients = {}
        self._registered_objects = {}

        self.signals = {
            "client_connected": kaa.notifier.Signal(),
            "client_closed": kaa.notifier.Signal()
        }


    def handle_connection(self):
        client_sock = self.socket.accept()[0]
        client_sock.setblocking(False)
        _debug(1, "New connection", client_sock)
        client = IPCChannel(self, client_sock)
        self.clients[client_sock] = client
        self.signals["client_connected"].emit(client)


    def close_connection(self, client):
        client.socket.close()
        del self.clients[client.socket]
        client.socket = None
        self.signals["client_closed"].emit(client)


    def register_object(self, obj, id):
        self._registered_objects[id] = obj


    def unregister_object(self, id):
        if id in self._registered_objects:
            del self._registered_objects[id]


    def close(self):
        for client in self.clients.values():
            client.socket.close()
        self.socket.close()


        
class IPCChannel:
    def __init__(self, server_or_address, sock = None):
        if not sock:
            if type(server_or_address) in types.StringTypes:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if type(server_or_address) == tuple:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(server_or_address)
            self.socket.setblocking(False)
            self.server = None
        else:
            self.socket = sock
            self.server = server_or_address

        self._rmon = kaa.notifier.SocketDispatcher(self.handle_read)
        self._rmon.register(self.socket.fileno(), kaa.notifier.IO_READ)

        self._wmon = kaa.notifier.SocketDispatcher(self.handle_write)
        #self._wmon.register(self.socket.fileno(), kaa.notifier.IO_WRITE)
        
        self.read_buffer = []
        self.write_buffer = ""

        self.last_seq = 0
        self.wait_queue = {}
        self._proxied_objects = {}
        self._default_timeout = 2.0

        self.signals = {
            "closed": kaa.notifier.Signal()
        }


    def set_default_timeout(self, timeout):
        self._default_timeout = timeout


    def handle_close(self):
        _debug(1, "Client closed", self.socket)
        _debug(1, "Current proxied objects", self._proxied_objects)
        self._rmon.unregister()
        self._wmon.unregister()
        if self.server:
            self.server.close_connection(self)
        else:
            self.socket.close()
            self.socket = None

        self.signals["closed"].emit()


    def handle_read(self):
        try:
            data = self.socket.recv(1024*1024)
        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to read
                # data on a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            data = None

        if not data:
            self.handle_close()
            return

        self.read_buffer.append(data)
        # Before we start into the loop, make sure we have enough data for
        # a full packet.  For very large packets (if we just pickled a huge
        # object), this saves the string.join() which can be very expensive.
        # (This is the reason we use a list for our read buffer.)
        buflen = reduce(lambda x, y: x + len(y), self.read_buffer, 0)
        if buflen < 4:
            return
        if len(self.read_buffer[0]) >= 4:
            packet_len = struct.unpack("l", self.read_buffer[0][:4])[0]
            if buflen < packet_len:
                return
            
        strbuf = string.join(self.read_buffer, "")
        self.read_buffer = []
        n = 0
        while 1:
            if len(strbuf) <= 4:
                self.read_buffer.append(str(strbuf))
                break
            packet_len = struct.unpack("l", strbuf[:4])[0]
            if len(strbuf) < packet_len + 4:
                _debug(1, "Short packet, need %d, have %d" % (packet_len, len(self.read_buffer)))
                self.read_buffer.append(str(strbuf))
                break
            packet = strbuf[4:4 + packet_len]
            strbuf = buffer(strbuf, 4 + packet_len)
            self.handle_packet(packet)
            n += 1


    def write(self, data):
        self.write_buffer += data
        if not self._wmon.active():
            self._wmon.register(self.socket.fileno(), kaa.notifier.IO_WRITE)


    def writable(self):
        return len(self.write_buffer) > 0


    def handle_write(self):
        if not self.writable():
            return

        try:
            sent = self.socket.send(self.write_buffer)
            self.write_buffer = self.write_buffer[sent:]
            if not self.write_buffer:
                self._wmon.unregister()
        except socket.error:
            self.socket = None


    def handle_packet(self, packet):
        # FIXME: loads() could raise an exception if trying to unpickle an
        # unknown object (like an exception).
        (seq, packet_type, data) = cPickle.loads(packet)
        if packet_type[:3] == "REP":
            _debug(1, "-> REPLY: seq=%d, type=%s, data=%d" % (seq, packet_type, len(packet)))
            if seq not in self.wait_queue:
                _debug(1,  "WARNING: received reply for unknown sequence (%d)" % seq)
                return

            if self.wait_queue[seq][1] == False:
                # If the second element of the wait queue is False, it means
                # this is a synchronous call.
                self.wait_queue[seq][1] = True
                self.wait_queue[seq][2] = (seq, packet_type, data)
            else:
                # Async call.  Just delete the wait queue entry for now.
                # TODO: notify a callback
                del self.wait_queue[seq]

        elif packet_type[:3] == "REQ":
            _debug(1, "-> REQUEST: seq=%d, type=%s, data=%d" % (seq, packet_type, len(packet)))
            request = packet_type[4:].lower()
            if not hasattr(self, "handle_request_%s" % request):
                return
            try:
                reply = getattr(self, "handle_request_%s" % request)(data)
            except "NOREPLY":
                # handle_request_XXX will raise "NOREPLY" to prevent us
                # from replying -- for oneway fnctions.
                pass
            except (SystemExit,):
                raise sys.exc_info()[0], sys.exc_info()[1]
            except:
                # Marshal exception.
                exstr = string.join(traceback.format_exception(sys.exc_type, sys.exc_value, sys.exc_traceback))
                self.reply(request, ("error", (sys.exc_info()[0], sys.exc_info()[1], exstr)), seq)
            else:
                self.reply(request, ("ok", reply), seq)


    def _send_packet(self, packet_type, data, seq = 0, timeout = 2.0):
        if not self.socket:
            raise IPCDisconnectedError("Remote end no longer connected")
        if seq == 0:
            seq = self.last_seq = self.last_seq + 1

        if packet_type[:3] == "REQ":
            _debug(1, "<- REQUEST: seq=%d, type=%s, data=%d" % (seq, packet_type, len(data)))
            self.wait_queue[seq] = [data, False, None]
            if timeout == 0:
                self.wait_queue[seq][1] = None
        else:
            _debug(1, "<- REPLY: seq=%d, type=%s, data=%d" % (seq, packet_type, len(data)))
        pdata = cPickle.dumps( (seq, packet_type, data), 2 )
        self.write(struct.pack("l", len(pdata)) + pdata)
        if packet_type[:3] == "REQ" and timeout > 0:
            t0 = time.time()
            while self.wait_queue[seq][1] == False and time.time() - t0 < timeout and self.socket:
                kaa.notifier.step()
        return seq


    def request(self, type, data, timeout = None):
        if timeout == None:
            timeout = self._default_timeout

        seq = self._send_packet("REQ_" + type, data, timeout = timeout)
        if not self.socket:
            raise IPCDisconnectedError
        # FIXME: if request doesn't block, wait_queue entry doesn't get removed
        if timeout > 0 and self.wait_queue[seq][1]:
            seq, type, (resultcode, data) = self.wait_queue[seq][2]
            del self.wait_queue[seq]
            #return seq, type, data
            if resultcode == "ok":
                return data
            elif resultcode == "error":
                data[0]._ipc_remote_tb = data[2].strip()
                raise data[0], data[1]
        elif timeout > 0:
            raise IPCTimeoutError


    def reply(self, type, data, seq):
        return self._send_packet("REP_" + type, data, seq)


    def handle_request_get(self, name):
        if not self.server:
            return None

        obj = self.server._registered_objects.get(name)
        if not obj:
            return None

        return self._proxy_data(obj)


    def handle_request_ping(self, foo):
        return True


    def handle_request_getattr(self, (objid, attr)):
        obj = self._get_proxied_object(objid)
        _debug(1, "-> getattr", type(obj), objid, attr)
        if attr == "__ipcstr__":
            return str(obj)

        value = getattr(obj, attr)
        return self._proxy_data(value)


    def handle_request_setattr(self, (objid, attr, value)):
        obj = self._get_proxied_object(objid)
        value = self._unproxy_data(value)
        _debug(1, "-> setattr", type(obj), objid, attr, value)
        # It'd be nice to raise NOREPLY here and make setattr oneway, but
        # we need to be able to send exceptions to the remote side.
        setattr(obj, attr, value)


    def handle_request_clone(self, objid):
        obj = self._get_proxied_object(objid)
        if not obj:
            return
        return obj


    def handle_request_call(self, (objid, args, kwargs)):
        _ipc_args = {}
        for arg in ("copy_result", "oneway"):
            if "__ipc_" + arg in kwargs:
                _ipc_args[arg] = kwargs["__ipc_" + arg]
                del kwargs["__ipc_" + arg]

        args = self._unproxy_data(args)
        obj = self._get_proxied_object(objid)
        result = obj(*args, **kwargs)

        if _ipc_args.get("oneway"):
            # This is kinda lame.  Raise this exception we catch in 
            # handle_rqeuest_call() to prevent replying.
            raise "NOREPLY"

        _debug(1, "-> () CALL %s" % obj.__name__)
        if _ipc_args.get("copy_result"):
            return result
        else:
            return self._proxy_data(result)
        

    def handle_request_callmeth(self, (objid, meth, args, kwargs)):
        args = self._unproxy_data(args)
        obj = self._get_proxied_object(objid)
        _debug(1, "-> () CALL METH: ", objid, meth)
        result = getattr(obj, meth)(*args, **kwargs)
        return self._proxy_data( result)

        
    def handle_request_decref(self, objid):
        if objid not in self._proxied_objects:
            return
        _debug(1, "-> Refcount-- on object", objid)
        self._decref_proxied_object(objid)


    def handle_request_incref(self, objid):
        if objid not in self._proxied_objects:
            return
        _debug(1, "-> Refcount++ on object", objid)
        self._incref_proxied_object(objid)


    def _decref_proxied_object(self, objid):
        if objid in self._proxied_objects:
            self._proxied_objects[objid][1] -= 1
            if self._proxied_objects[objid][1] == 0:
                _debug(1, "-> Refcount=0; EXPIRING object", objid, type(self._proxied_objects[objid][0]))
                del self._proxied_objects[objid]
        else:
            _debug(1, "<- Refcount-- on object", objid)
            self.request("DECREF", objid, timeout = 0)


    def _incref_proxied_object(self, objid):
        if objid in self._proxied_objects:
            self._proxied_objects[objid][1] += 1
        else:
            _debug(1, "<- Refcount++ on object", objid)
            self.request("INCREF", objid, timeout = 0)
        

    def _get_proxied_object(self, objid):
        return self._proxied_objects[objid][0]


    def _make_objid(self, obj):
        if callable(obj) and hasattr(obj, "im_self"):
            return hex(abs(id(obj.im_self))) + "-meth-" + obj.__name__
        else:
            return hex( abs(id(obj)) )


    def _proxy_object(self, obj):
        objid = self._make_objid(obj)
        if objid in self._proxied_objects:
            # Increase refcount
            self._proxied_objects[objid][1] += 1
        else:
            self._proxied_objects[objid] = [obj, 1]

        _debug(1, "PROXY: IPCProxy object created from", type(obj), objid)
        return IPCProxy(objid, obj)


    def _proxy_data(self, data, unproxy = False):
        # FIXME: _proxy_data and _proxy_data need serious refactoring

        immutable_types = types.StringTypes + (types.IntType, types.LongType,
                          types.TupleType,  types.BooleanType, types.SliceType,
                          types.FloatType, types.NoneType)

        if type(data) not in immutable_types:
            if isproxy(data):
                objid = data._ipc_obj
                data._ipc_client = self
                # If we're unproxying and object is local, return the local object
                if unproxy and objid in self._proxied_objects:
                    return self._proxied_objects[objid][0]
                else:
                    # Object is remote and we're not unproxying, incref it.
                    # XXX: this might be wrong.
                    if not unproxy:
                        self._incref_proxied_object(objid)
                    return data
            else:
                if not unproxy:
                    return self._proxy_object(data)
                else:
                    return data
                
        elif type(data) in (types.TupleType, ):
            proxied_data = []
            for item in data:
                proxied_data.append(self._proxy_data(item, unproxy))
            # Convert back to a tuple
            if type(data) == types.TupleType:
                proxied_data = tuple(proxied_data)
            return proxied_data
        else:
            return data

    def _unproxy_data(self, data):
        return self._proxy_data(data, unproxy = True)
    
    ############################################################################

    def get_object(self, name):
        # id() of object on remote end
        proxy = self.request("GET", name)
        proxy = self._unproxy_data(proxy)
        return proxy

    def ping(self):
        start = time.time()
        if self.request("PING", None):
            return time.time() - start
        return False


class IPCClient(IPCChannel):
    pass



class IPCProxy(object):
    
    def __new__(cls, objid = None, orig_object = None):
        if orig_object:
            cls = get_proxy_type(orig_object.__class__.__name__)
        i = super(IPCProxy, cls).__new__(cls, objid, orig_object)
        return i


    def __init__(self, objid = None, orig_object = None):
        self._ipc_obj = objid
        self._ipc_cache_methods = {}
        self._ipc_client = None
        self._ipc_cache_special_attrs = {}

        if orig_object:
            self._ipc_callable = callable(orig_object)
            if type(orig_object) in types.__dict__.values():
                for (name, t) in types.__dict__.items():
                    if t == type(orig_object):
                        self._ipc_orig_type = "\x01" + name
            else:
                try:
                    self._ipc_orig_type = cPickle.dumps(orig_object.__class__)
                except:
                    self._ipc_orig_type = None
            self._ipc_class = orig_object.__class__

            for attr in dir(orig_object):
                if not attr.startswith("__") and attr not in ("next",):
                    continue
                self._ipc_cache_special_attrs[attr] = callable(getattr(orig_object, attr))


    def __del__(self):
        # Test _debug function too.  If it's None it means we're on shutdown.
        # This is just a hack to silence "ignored exception" messages.
        if not self._ipc_client or not _debug:
            return

        if self._ipc_obj in self._ipc_client._proxied_objects:
            # Local proxy
            self._ipc_client._decref_proxied_object(self._ipc_obj)
        elif self._ipc_client.socket:
            self._ipc_client.request("DECREF", self._ipc_obj, timeout = 0)
        

    def _ipc_get_str(self):
        if self._ipc_client:
            if self._ipc_client.socket:
                try:
                    return self._ipc_client.request("GETATTR", (self._ipc_obj, "__ipcstr__"))
                except KeyError: 
                    return "<unknown>"
                except:
                    pass
            return "<disconnected>"
            #f._ipc_client = self._ipc_client
            #return f()


    def _ipc_get_client(self):
        return self._ipc_client


    def _ipc_local(self):
        return hasattr(self, "_ipc_client") and (not self._ipc_client or \
               self._ipc_obj in self._ipc_client._proxied_objects)


    def _ipc_clone(self):
        return self._ipc_client.request("CLONE", self._ipc_obj)


    def __str__(self):
        #t = "<IPCProxy object at 0x%x; proxying for " % abs(id(self))
        t = "<Proxied " + ("remote", "local")[int(self._ipc_local())]
        t += " object %s>" % self._ipc_get_str()
        return t


    def __getattribute__(self, attr):
        #print "GET", attr
        if attr == "__class__" and not self._ipc_local() and self._ipc_class:
            #print "Spoofing type", self, self._ipc_class
            return self._ipc_class
        if attr.startswith("_ipc_") or self._ipc_local():
            return object.__getattribute__(self, attr)
        elif attr in self._ipc_cache_methods:
            return self._ipc_cache_methods[attr]
        elif attr.startswith("__") and attr not in self._ipc_cache_special_attrs: 
            raise AttributeError, "Object has no attribute '%s'" % attr

        value = self._ipc_client.request("GETATTR", (self._ipc_obj, attr))
        value = self._ipc_client._unproxy_data(value)
        if callable(value):
            self._ipc_cache_methods[attr] = value
        return value


    def __setattr__(self, attr, value):
        if attr.startswith("_ipc_") or attr.startswith("__"):
            object.__setattr__(self, attr, value)
            return

        value = self._ipc_client._proxy_data(value)
        self._ipc_client.request("SETATTR", (self._ipc_obj, attr, value))


    def __call__(self, *args, **kwargs):
        t0=time.time()
        if self._ipc_callable == False:
            raise TypeError, "Object not callable"
        elif self._ipc_callable == None:
            try:
                getattr(self, "__call__")
                self._ipc_callable = True
            except AttributeError:
                self._ipc_callable = False
        
        args = self._ipc_client._proxy_data(args)
        if kwargs.get("__ipc_oneway"):
            result = self._ipc_client.request("CALL", (self._ipc_obj, args, kwargs), 0)
        else:    
            result = self._ipc_client.request("CALL", (self._ipc_obj, args, kwargs))
            result = self._ipc_client._unproxy_data(result)

        _debug(1, "TIME: invocation took %.04f" % (time.time()-t0))
        return result


    def _ipc_meth(self, name, args):
        result = self._ipc_client.request("CALLMETH", (self._ipc_obj, name, self._ipc_client._proxy_data(args), {}))
        return self._ipc_client._unproxy_data(result)
