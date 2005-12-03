#
# TODO: document me!
#
# Simple usage example:
#   On server:
#       class Foo:
#           def bar(self):
#               return 42, self
#       foo = Foo()
#       ipc = IPCServer("ipc.socket", auth_secret = "foobar")
#       ipc.register_object(foo, "foo")
#
#   On client:
#       ipc = IPCClient("ipc.socket", auth_secret = "foobar")
#       foo = ipc.get_object("foo")
#       print foo.bar()

import logging
import socket, os, select, time, types, struct, cPickle, thread, sys, sha
import traceback, string, copy_reg
from new import classobj
import kaa.notifier
import kaa

log = logging.getLogger('notifier')

IPC_DEFAULT_TIMEOUT = 5.0

DEBUG=1
DEBUG=0

def _debug(level, text, *args):
    if DEBUG  >= level:
        for arg in args:
            text += " " + str(arg)
        print text

def _pickle_slice(slice):
    return _unpickle_slice, (slice.start, slice.stop, slice.step)
def _unpickle_slice(start, stop, step):
    return slice(start, stop, step)
copy_reg.pickle(slice, _pickle_slice, _unpickle_slice)

def _pickle_buffer(buffer):
    return _unpickle_buffer, (str(buffer),)
def _unpickle_buffer(s):
    return buffer(s)
copy_reg.pickle(buffer, _pickle_buffer, _unpickle_buffer)

def _get_proxy_type(name):
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
    cls = _get_proxy_type(clsname)
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



class IPCDisconnectedError(Exception):
    pass

class IPCTimeoutError(Exception):
    pass

class IPCAuthenticationError(Exception):
    pass

class IPCRemoteException(Exception):
    def __init__(self, remote_exc, remote_value, remote_tb):
        self.exc = remote_exc
        self.val = remote_value
        self.tb = remote_tb

    def __str__(self):
        return "A remote exception has occurred.  Here is the remote traceback:\n%s" % self.tb


class IPCServer:

    def __init__(self, address, auth_secret = None):
        self._auth_secret = auth_secret
        if type(address) in types.StringTypes:
            if address.find('/') == -1:
                # create socket in kaa temp dir
                address = '%s/%s' % (kaa.TEMP, address)
                
            if os.path.exists(address):
                # maybe a server is already running at this address, test it
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.connect(address)
                except socket.error, e:
                    if e[0] == 111:
                        # not running, everything is fine
                        log.info('remove socket from dead server')
                    else:
                        # some error we do not expect
                        raise e
                else:
                    # server already running
                    raise IOError('server already running')
                os.unlink(address)
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.address = address
            kaa.signals["shutdown"].connect_weak(self.close)
            
        elif type(address) == tuple:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket.setblocking(False)
        self.socket.bind(address)
        self.socket.listen(5)
        self._monitor = kaa.notifier.WeakSocketDispatcher(self.handle_connection)
        self._monitor.register(self.socket.fileno())
        # Remove socket file and close clients on shutdown
        kaa.signals["shutdown"].connect_weak(self.close)
        
        self.clients = {}
        self._registered_objects = {}

        self.signals = {
            "client_connected": kaa.notifier.Signal(),
            "client_closed": kaa.notifier.Signal()
        }


    def __del__(self):
        self.close()

    def handle_connection(self):
        client_sock = self.socket.accept()[0]
        client_sock.setblocking(False)
        _debug(1, "New connection", client_sock)
        client = IPCChannel(self, auth_secret = self._auth_secret, sock = client_sock)
        self.clients[client_sock] = client
        self.signals["client_connected"].emit(client)


    def client_closed(self, client):
        if client.socket in self.clients:
            del self.clients[client.socket]
        self.signals["client_closed"].emit(client)


    def register_object(self, obj, id):
        self._registered_objects[id] = obj


    def unregister_object(self, id):
        if id in self._registered_objects:
            del self._registered_objects[id]


    def close(self):
        _debug(1, "Closing IPCServer, clients:", self.clients)
        for client in self.clients.values():
            client.handle_close()

        if self.socket:
            self.socket.close()

        if type(self.address) in types.StringTypes and os.path.exists(self.address):
            os.unlink(self.address)

        self.socket = None
        self._monitor.unregister()
        kaa.signals["shutdown"].disconnect(self.close)
        
        
class IPCChannel(object):
    def __init__(self, server_or_address, auth_secret = None, sock = None):
        if not sock:
            if type(server_or_address) in types.StringTypes:
                server_or_address = '%s/%s' % (kaa.TEMP, server_or_address)
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if type(server_or_address) == tuple:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(server_or_address)
            self.socket.setblocking(False)
            self.server = None
        else:
            self.socket = sock
            self.server = server_or_address

        self._rmon = kaa.notifier.WeakSocketDispatcher(self.handle_read)
        self._rmon.register(self.socket.fileno(), kaa.notifier.IO_READ)

        self._wmon = kaa.notifier.WeakSocketDispatcher(self.handle_write)
        #self._wmon.register(self.socket.fileno(), kaa.notifier.IO_WRITE)

        self.signals = {
            "closed": kaa.notifier.Signal()
        }
        
        self.read_buffer = []
        self.write_buffer = ""

        self.last_seq = 0
        self._wait_queue = {}
        self._proxied_objects = {}
        self._default_timeout = IPC_DEFAULT_TIMEOUT
        self._auth_secret = auth_secret
        self._authenticated = False
        
        if not self.server and self._auth_secret != None:
            self._pending_challenge = self._get_rand_value()
            self.request("auth", (self._pending_challenge, "", ""))
        else:
            self._pending_challenge = None


    def __del__(self):
        self.handle_close()

    def set_default_timeout(self, timeout):
        self._default_timeout = timeout


    def handle_close(self):
        _debug(1, "Client closed", self.socket)
        _debug(1, "Current proxied objects", self._proxied_objects)
        self._rmon.unregister()
        self._wmon.unregister()
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.server:
            self.server.client_closed(self)

        self._wait_queue = {}
        self._proxied_objects = {}
        self.signals["closed"].emit()
        kaa.signals["shutdown"].disconnect(self.handle_close)


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
        except:
            data = None

        if not data:
            self.handle_close()
            return

        header_size = struct.calcsize("I20sI")
        self.read_buffer.append(data)
        # Before we start into the loop, make sure we have enough data for
        # a full packet.  For very large packets (if we just received a huge
        # pickled object), this saves the string.join() which can be very 
        # expensive.  (This is the reason we use a list for our read buffer.)
        buflen = reduce(lambda x, y: x + len(y), self.read_buffer, 0)
        if buflen < header_size:
            return
        if buflen > 512 and self._auth_secret != None and self._authenticated == False:
            # 512 bytes is plenty for authentication handshake.  Any more than
            # that and something isn't right.
            log.warning("Too much data received from remote end before authentication; disconnecting")
            self.handle_close()
            return

        # Ensure the first block in the read buffer is big enough for a full
        # packet header.  If it isn't, then we must have more than 1 block in
        # the buffer, so keep merging blocks until we have a block big enough
        # to be a header.  If we're here, it means that buflen >= header_size,
        # so we can safely loop.
        while len(self.read_buffer[0]) < header_size:
            self.read_buffer[0] += self.read_buffer.pop(1)

        # Make sure the the buffer holds enough data as indicated by the
        # payload size in the header.
        payload_len = struct.unpack("I20sI", self.read_buffer[0][:header_size])[2]
        if buflen < payload_len + header_size:
            return

        # At this point we know we have enough data in the buffer for the
        # packet, so we merge the array into a single buffer.
        strbuf = string.join(self.read_buffer, "")
        self.read_buffer = []
        while 1:
            if len(strbuf) <= header_size:
                if len(strbuf) > 0:
                    self.read_buffer.append(str(strbuf))
                break
            seq, packet_type, payload_len = struct.unpack("I20sI", strbuf[:header_size])
            if len(strbuf) < payload_len + header_size:
                # We've also received portion of another packet that we
                # haven't fully received yet.  Put back to the buffer what
                # we have so far, and we can exit the loop.
                _debug(1, "Short packet, need %d, have %d" % (payload_len, len(self.read_buffer)))
                self.read_buffer.append(str(strbuf))
                break

            # Grab the payload for this packet, and shuffle strbuf to the
            # next packet.
            payload = strbuf[header_size:header_size + payload_len]
            strbuf = buffer(strbuf, header_size + payload_len)
            self.handle_packet(seq, packet_type.strip("\x00"), payload)


    def write(self, data):
        self.write_buffer += data
        if not self._wmon.active():
            _debug(2, "Registered write monitor, write buffer length=%d" % len(self.write_buffer))
            self._wmon.register(self.socket.fileno(), kaa.notifier.IO_WRITE)


    def writable(self):
        return len(self.write_buffer) > 0


    def handle_write(self):
        if not self.writable():
            return

        _debug(2, "Handle write, write buffer length=%d" % len(self.write_buffer))
        try:
            sent = self.socket.send(self.write_buffer)
            self.write_buffer = self.write_buffer[sent:]
            if not self.write_buffer:
                self._wmon.unregister()
        except socket.error, (errno, msg):
            if errno == 11:
                # Resource temporarily unavailable -- we are trying to write
                # data to a socket when none is available.
                return
            # If we're here, then the socket is likely disconnected.
            self.handle_close()


    def handle_packet(self, seq, packet_type, payload):
        # Untaint packet_type.
        if len(packet_type) <= 4 or packet_type[:3] not in ("REP", "REQ") or \
           not packet_type[4:].isalpha(): 
            log.warning("Bad request from remote; disconnecting.")
            return self.handle_close()

        # packet_type is safe now.  It is <= 20 bytes (assured by struct.unpack
        # in handle_read() and consists of only alpha chars.  seq is guaranteed
        # to be an integer (returned by struct.unpack) but it may not be a
        # valid sequence number.  payload is tainted and could contain 
        # something nasty.

        prefix = packet_type[:3].lower()
        command = packet_type[4:].lower()

        if (self._auth_secret != None and self._authenticated == False) or command == "auth":
            # We're waiting for authentication or have received an auth packet.
            # Handle this packet using paranoid _handle_auth_packet method.
            data = self._handle_auth_packet(seq, prefix, command, payload)
            if not data:
                return
        else:
            # Here we are either authenticated or we don't require auth.  We
            # assume it's safe to unpickle the payload.
            try:
                data = cPickle.loads(payload)
            except:
                log.warning("Received packet failed to unpickle")
                return

        # If we're here, we're either authenticated or we don't require
        # authentication, or else the auth has just failed.  In the latter 
        # case, 'data' does not contain anything from the remote.

        if prefix == "rep":
            if  seq not in self._wait_queue:
                log.warning("Received reply for unknown sequence (%d)" % seq)
                return

            _debug(1, "-> REPLY: seq=%d, command=%s, data=%d" % (seq, command, len(payload)))

            if self._wait_queue[seq][1] == False:
                # If the second element of the wait queue is False, it means
                # this is a synchronous call.
                self._wait_queue[seq][1] = True
                self._wait_queue[seq][2] = (seq, packet_type, data)
            else:
                result_cb = self._wait_queue[seq][4]
                result = self.handle_reply(seq, packet_type, data)
                if result_cb:
                    # Async call, invoke result callback.
                    # TODO: be smarter about remote exceptions
                    result_cb(self._proxy_data(result))
        else:
            _debug(1, "-> REQUEST: seq=%d, command=%s, data=%d" % (seq, command, len(payload)))
            if not hasattr(self, "handle_request_%s" % command):
                print "handle_request_%s doesn't exist!" % command
                return
            try:
                reply = getattr(self, "handle_request_%s" % command)(data)
            except "NOREPLY":
                # handle_request_XXX will raise "NOREPLY" to prevent us
                # from replying -- for oneway functions.
                pass
            except (SystemExit,):
                raise sys.exc_info()[0], sys.exc_info()[1]
            except IPCAuthenticationError, data:
                self.reply(command, ("auth", data), seq)
            except:
                # Marshal exception.
                if sys.exc_info()[0] not in (StopIteration,):
                    log.exception("Exception occurred in IPC call")
                exstr = string.join(traceback.format_exception(sys.exc_type, sys.exc_value, sys.exc_traceback))
                self.reply(command, ("error", (sys.exc_info()[0], sys.exc_info()[1], exstr)), seq)
            else:
                self.reply(command, ("ok", reply), seq)


    def _get_rand_value(self):
        """
        Returns a 20 byte value which is computed as a SHA hash of the
        current time concatenated with 64 bytes from /dev/urandom.  This
        value is not by design a nonce, but in practice it probably is.
        """
        rbytes = file("/dev/urandom").read(64)
        return sha.sha(str(time.time()) + rbytes).digest()


    def _get_challenge_response(self, challenge, salt = None):
        """
        Generate a response for the challenge based on the auth secret
        supplied to the constructor.  This hashes twice to prevent against
        certain attacks on the hash function.  If salt is not None, it is
        the value generated by the remote end that was used in computing 
        their response.  If it is None, a new 20-byte salt is generated
        and used in computing our response.  
        
        """
        if self._auth_secret == None:
            return "", ""
        if salt == None:
            salt = self._get_rand_value()
        m = challenge + self._auth_secret + salt
        return sha.sha(sha.sha(m).digest() + m).digest(), salt


    def _handle_auth_packet(self, seq, prefix, command, payload):
        """
        This function handles any packet received by the remote end while
        we are waiting for authentication, as well as all 'auth' packets.

        When no shared secret is specified in the IPCChannel constructor, all
        incoming connections are considered implicitly authenticated.

        Design goals of authentication:
           * prevent unauthenticated connections from executing IPC commands
             other than 'auth' commands.
           * prevent unauthenticated connections from causing denial-of-
             service at or above the IPC layer.
           * prevent third parties from learning the shared secret by 
             eavesdropping the channel.
              
        Non-goals:
           * provide any level of security whatsoever subsequent to successful
             authentication.
           * detect in-transit tampering of authentication by third parties
             (and thus preventing successful authentication).

        The parameters seq, prefix and command are untainted and safe.
        The parameter payload is potentially dangerous and this function
        must handle any possible malformed payload gracefully.

        Authentication is a 4 step process and once it has succeeded, both
        sides should be assured that they share the same authentication
        secret.  It uses a simple challenge-response scheme.  The party
        responding to a challenge will hash the response with a locally
        generated salt to prevent chosen plaintext attacks.  The client 
        initiates authentication.

           1. Client sends challenge to server.
           2. Server receives challenge, computes response, generates a
              counter-challenge and sends both to the client in reply.
           3. Client receives response to its challenge in step 1 and the
              counter-challenge from server in step 2.  Client validates
              server's response.  If it fails, client raises 
              IPCAuthenticationError exception but does not disconnect.
              If it succeeds, client sends response to server's counter-
              challenge.
           4. Server receives client's response and validates it.  If it
              fails, it disconnects immediately.  If it succeeds, it allows
              the client to send non-auth packets.

        Step 1 happens in the constructor.  Steps 2-4 happen in this function.
        3 packets are sent in this handshake (steps 1-3).

        WARNING: once authentication succeeds, there is implicit full trust.
        There is no security after that point, and it must be assumed that
        the client can invoke arbitrary calls on the server, and vice versa.

        Also, individual packets aren't authenticated.  Once each side has
        sucessfully authenticated, this scheme cannot protect against 
        hijacking or denial-of-service attacks.

        One goal is to restrict the code path taken packets sent by 
        unauthenticated connections.  That path is:

           handle_read() -> handle_packet() -> _handle_auth_packet()

        Therefore these functions must be able to handle malformed and/or
        potentially malicious data on the channel.  When these methods calls
        other functions, it must do so only with untainted data.  Obviously one
        assumption is that the underlying python calls made in these methods
        (particularly struct.unpack) aren't susceptible to attack.
        """
        
        if command != "auth":
            # Received a non-auth command while expecting auth.
            if prefix == "req":
                # Send authentication-required reply.
                self.reply(command, ("auth", 0), seq)
            # Hang up.
            self.handle_close()
            return

        # We have an authentication packet.
        try:
            # Payload could safely be longer than 20+20+20 bytes, but if it
            # is, something isn't quite right.  We'll be paranoid and
            # disconnect unless it's exactly 60 bytes.
            assert(len(payload) == 60)

            # Unpack the auth packet payload into three separate 20 byte 
            # strings: the challenge, response, and salt.  If challenge is
            # not NULL (i.e. '\x00' * 20) then the remote is expecting a
            # a response.  If response is not NULL then salt must also not
            # be NULL, and the salt is used along with the previously sent
            # challenge to validate the response.
            challenge, response, salt = struct.unpack("20s20s20s", payload)
        except:
            log.warning("Malformed authentication packet from remote; disconnecting.")
            self.handle_close()
            return
        
        # At this point, challenge, response, and salt are 20 byte strings of
        # arbitrary binary data.  They're considered benign.
        if prefix == "req":
            # Step 2: We've received a challenge.  If we've already sent a
            # challenge (which is the case if _pending_challenge is not None),
            # then something isn't right.  This could be a DoS so we'll
            # disconnect immediately.
            if self._pending_challenge:
                self._pending_challenge = None
                self.handle_close()
                return

            # Otherwise send the response, plus a challenge of our own.
            response, salt = self._get_challenge_response(challenge)
            self._pending_challenge = self._get_rand_value()
            self.reply("auth", (self._pending_challenge, response, salt), seq)
            return
        else:
            # Received a reply to an auth request.
            if self._pending_challenge == None:
                # We've received a reply packet, but we haven't sent a 
                # challenge.  Something isn't right, so disconnect.
                self.handle_close()
                return

            # Step 3/4: We are expecting a response to our previous challenge
            # (either the challenge from step 1, or the counter-challenge from
            # step 2).  First compute the response we expect to have received
            # based on the challenge sent earlier, our shared secret, and the
            # salt that was generated by the remote end.
            expected_response = self._get_challenge_response(self._pending_challenge, salt)[0]
            # We have our response, so clear the pending challenge.
            self._pending_challenge = None
            # Now check to see if we were sent what we expected to receive.
            if response != expected_response:
                # Remote failed our challenge.  If we're a server,
                # disconnect immediately.  The client should already know
                # the authentication failed because our first reply would
                # have failed.  If we're a client, simulate an auth 
                # failure return code so an exception gets raised.
                if self.server:
                    self.handle_close()
                    return
                else:
                    return ("auth", 1)

            # Challenge response was good, so the remote is considered 
            # authenticated now.
            self._authenticated = True

            # If remote has issued a counter-challenge along with their
            # response (step 2), we'll respond.  Unless something fishy is
            # going on, this should always succeed on the remote end, because
            # at this point our auth secrets must match.  A challenge is
            # considered issued if it is not NULL ('\x00' * 20).  If no
            # counter-challenge was received as expected from step 2, then
            # authentication is only one-sided (we trust the remote, but the
            # remote won't trust us).  In this case, things won't work
            # properly, but there are no negative security implications.
            if len(challenge.strip("\x00")) != 0:
                response, salt = self._get_challenge_response(challenge)
                self.reply("auth", ("", response, salt), seq)

            # If we're a client, simulate a valid return code so that if the
            # caller is blocking, it will return (or its async callback will
            # get called).
            if not self.server:
                return ("ok", None)



    def _send_packet(self, packet_type, data, seq = 0, timeout = None, reply_cb = None):
        if not self.socket:
            return

        if timeout == reply_cb == None:
            timeout = self._default_timeout
        if seq == 0:
            seq = self.last_seq = self.last_seq + 1
    
        
        assert(len(packet_type) <= 20)
        # Normally command data gets pickled, but auth commands are a special
        # case.  We don't use pickling for authentication because it's
        # dangerous to unpickle something of dubious origin.
        if packet_type[4:].lower() == "auth":
            challenge, response, salt = [ str(x) for x in data ]
            pdata = struct.pack("20s20s20s", challenge, response, salt)
        else:
            pdata = cPickle.dumps(data, 2)

        if packet_type[:3] == "REQ":
            _debug(1, "<- REQUEST: seq=%d, type=%s, data=%d, timeout=%d" % (seq, packet_type, len(pdata), timeout))
            self._wait_queue[seq] = [data, None, None, time.time(), reply_cb]
            if timeout > 0:
                self._wait_queue[seq][1] = False
        else:
            _debug(1, "<- REPLY: seq=%d, type=%s, data=%d" % (seq, packet_type, len(pdata)))

        self.write(struct.pack("I20sI", seq, packet_type, len(pdata)) + pdata)
        if not self.socket:
            return
        if packet_type[:3] == "REQ" and timeout > 0:
            t0 = time.time()
            while self.socket and self._wait_queue[seq][1] == False and time.time() - t0 < timeout:
                kaa.notifier.step()
        else:
            self.handle_write()
        _debug(1, "<- REQUEST COMPLETE: seq=%d, type=%s" % (seq, packet_type))
        return seq


    def handle_reply(self, seq, type, (resultcode, data)):
        del self._wait_queue[seq]
        #return seq, type, data
        if resultcode == "ok":
            return data
        elif resultcode == "auth":
            if data == 0:
                raise IPCAuthenticationError(0, "Remote requires authentication.")
            elif data == 1:
                raise IPCAuthenticationError(1, "Authentication failure.")
            else:
                raise IPCAuthenticationError(-1, "Unknown authentication error.")
        elif resultcode == "error":
            if data[0] in (StopIteration,):
                raise data[0](data[1])
            raise IPCRemoteException(data[0], data[1], data[2].strip())


    def request(self, type, data, timeout = None, reply_cb = None):
        if timeout == reply_cb == None:
            timeout = self._default_timeout

        seq = self._send_packet("REQ_" + type, data, timeout = timeout, reply_cb = reply_cb)
        if not self.socket:
            if not self.server:
                # Raise exception if we're a client.
                raise IPCDisconnectedError
            return

        # FIXME: if timeout == 0 and no reply received, wait_queue entry 
        # doesn't get removed until the socket is disconnected.  There should
        # be some expiry on wait queue entries.
        if timeout > 0 and self._wait_queue[seq][1]:
            return self.handle_reply(*self._wait_queue[seq][2])
        elif timeout > 0:
            del self._wait_queue[seq]
            raise IPCTimeoutError, (type,)


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
        kwargs = self._unproxy_data(kwargs)
        obj = self._get_proxied_object(objid)
        _debug(1, "-> () CALL %s" % obj.__name__)
        result = obj(*args, **kwargs)

        if _ipc_args.get("oneway"):
            # This is kinda lame.  Raise this exception we catch in 
            # handle_rqeuest_call() to prevent replying.
            raise "NOREPLY"

        if _ipc_args.get("copy_result"):
            return result
        else:
            return self._proxy_data(result)
        

    def handle_request_callmeth(self, (objid, meth, args, kwargs)):
        args = self._unproxy_data(args)
        obj = self._get_proxied_object(objid)
        _debug(1, "-> () CALL METH: ", objid, meth)
        result = getattr(obj, meth)(*args, **kwargs)
        return self._proxy_data(result)

        
    def handle_request_decref(self, objid):
        if objid not in self._proxied_objects:
            return
        _debug(1, "-> Refcount-- on local object", objid)
        self._decref_proxied_object(objid)
        raise "NOREPLY"


    def handle_request_incref(self, objid):
        if objid not in self._proxied_objects:
            return
        _debug(1, "-> Refcount++ on local object", objid)
        self._incref_proxied_object(objid)
        raise "NOREPLY"


    def _decref_proxied_object(self, objid):
        if objid in self._proxied_objects:
            self._proxied_objects[objid][1] -= 1
            if self._proxied_objects[objid][1] == 0:
                _debug(1, "-> Refcount=0; EXPIRING local proxied object", objid, type(self._proxied_objects[objid][0]))
                del self._proxied_objects[objid]
        else:
            _debug(1, "<- Refcount-- on remote object", objid)
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
            _debug(1, "PROXY: (EXISTING) IPCProxy object created from", type(obj), objid)
        else:
            self._proxied_objects[objid] = [obj, 1]
            _debug(1, "PROXY: (NEW) IPCProxy object created from", type(obj), objid)

        return IPCProxy(objid, obj)


    def _proxy_data(self, data, unproxy = False):
        # FIXME: _proxy_data and _proxy_data need serious refactoring

        immutable_types = types.StringTypes + (types.IntType, types.LongType,
                          types.TupleType,  types.BooleanType, types.SliceType,
                          types.FloatType, types.NoneType)

        if type(data) not in immutable_types:
            if is_proxy(data):
                objid = data._ipc_obj
                data._ipc_client = self
                # If we're unproxying and object is local, return the local object
                if unproxy and objid in self._proxied_objects:
                    return self._proxied_objects[objid][0]

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
    def __init__(self, server_or_address, auth_secret = None, sock = None):
        super(IPCClient, self).__init__(server_or_address, auth_secret, sock)
        # IPCChannels that are created by server will be closed on shutdown
        # by IPCServer.close, but for IPCClients, we need to add our own 
        # handler.
        kaa.signals["shutdown"].connect_weak(self.handle_close)



class IPCProxy(object):
    
    def __new__(cls, objid = None, orig_object = None):
        if orig_object != None:
            cls = _get_proxy_type(orig_object.__class__.__name__)
        i = super(IPCProxy, cls).__new__(cls, objid, orig_object)
        return i


    def __init__(self, objid = None, orig_object = None):
        self._ipc_obj = objid
        self._ipc_cache_methods = {}
        self._ipc_client = None
        self._ipc_cache_special_attrs = {}

        if orig_object != None:
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

        # Drop our reference to the proxy -- if the proxy is remote, this
        # could raise an IPCDisconnectedError, which we won't worry about.
        try:
            self._ipc_client._decref_proxied_object(self._ipc_obj)
        except IPCDisconnectedError:
            pass

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
        _debug(2, "IPCProxy.__getattribute__: %s" % attr)
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
        timeout = reply_cb = None
        if kwargs.get("__ipc_timeout"):
            timeout = kwargs.get("__ipc_timeout")
        if kwargs.get("__ipc_oneway") or kwargs.get("__ipc_async"):
            timeout = 0
        if kwargs.get("__ipc_async"):
            reply_cb = kwargs["__ipc_async"]
            assert(callable(reply_cb))
            del kwargs["__ipc_async"]

        result = self._ipc_client.request("CALL", (self._ipc_obj, args, kwargs), timeout, reply_cb)
        if timeout != 0:
            result = self._ipc_client._unproxy_data(result)

        _debug(1, "TIME: invocation took %.04f" % (time.time()-t0))
        return result


    def _ipc_meth(self, name, args):
        result = self._ipc_client.request("CALLMETH", (self._ipc_obj, name, self._ipc_client._proxy_data(args), {}))
        return self._ipc_client._unproxy_data(result)



def is_proxy(obj):
    # Not foolproof, but good enough for me.
    return hasattr(obj, "_ipc_obj")

def get_ipc_from_proxy(obj):
    if not is_proxy(obj):
        return None
    return obj._ipc_get_client()


def is_proxy_alive(obj):
    client = get_ipc_from_proxy(obj)
    if not client:
        return False
    # If remote has disconnected, find out now.
    client.handle_read()
    return client.socket != None
