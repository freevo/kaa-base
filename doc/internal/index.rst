.. _internal:

Kaa Internals
=============

Module Importing
----------------

In large and complex Python libraries, it is often difficult to avoid circular
importing.  For example, *main*, which provides functions to manage the
kaa mainloop, requires *thread* to ensure that :func:`kaa.main.stop` runs
in the main thread.  *thread* requires *async* so that :class:`~kaa.ThreadInProgress`
can subclass :class:`~kaa.InProgress`.  *async* in turn requires *main*
in order to run the main loop for :meth:`kaa.InProgress.wait`.

Import cycles can generally be handled in several different ways:
 #. Consolidate all code involved in import cycles into the same file to
    eliminate the circular dependencies altogether.
 #. Use only absolute imports (``import foo.bar``) and never relative imports
    (``from foo import bar``), and move imports that generate import cycles
    to the bottom of the file.
 #. Import at function invocation time, just before the module is needed.  This
    will work for most scenarios, but not when you want to subclass a class
    defined in another module.

The first option is usually the simplest and most reliable, but for complex
dependencies can involve merging considerable amounts of code, which makes
maintenance more complicated.  In the case of Kaa, it would involve merging all
the code related to signals, threads, timers, coroutines, generators, async
(InProgress) and the mainloop.  This would result in a monstrous, nearly
5000 line file.

The second option would require explicit absolute importing of all modules
inside the framework (``import kaa.async``) which would preclude being able to
import directly from the source tree, which is useful for debugging and
bootstrapping the installation.  It also splits up imports, burying the circular
imports at the bottom of the file, and relies on proper comments to explain
what's happening.  Managing circular dependencies this way has shown to be
fragile.

The third option sounds tempting if it's possible (i.e. the circular dependency
is truly only needed at runtime, not at compile time).  However this can be
volatile and can result in deadlocks in certain circumstances.  Generally
we have found that importing a module that hasn't been imported already from
the main thread should be avoided.  However if the module is already imported,
it is safe to import it from a thread.

The solution chosen for Kaa is a combination of the first and third options.
Namely:

 * most of the nastier circular dependencies have been avoided by moving
   the Object, Signal, Signals classes, and the code used to manage the
   thread notifier pipe and callback queuing for mainthread invocation
   (*CoreThreading*) into one file ``core.py``
 * the remaining (three) circular dependencies are resolved by performing
   run-time imports; the lazy importing code has been modified to load
   the required modules up-front to prevent (or at least mitigate) these
   modules from being imported for the first time inside a thread.

The current circular dependencies (which are being handled by importing
at function invocation time) are:

 * *core* requires *async* (for Signal.__inprogress__() and Signals.any() and
   .all()); *async* requires *core* (for everything).
 * *async* requires *timer* (for InProgress.timeout()); *timer* requires
   *thread* (for threaded decorator); *thread* needs *async* (so that
   ThreadInProgress can subclass InProgress).
 * *async* requires *main* (InProgress.wait() calls main.loop()); *main*
   requires *thread* (for threaded decorator, and thread.killall());
   *thread* requires *async* (for the reason explained above).


There are a number of "core" modules that must be imported as a group to ensure
that none of the modules imported at function invocation time are imported
for the first time in a thread.  These are *core*, *nf_wrapper*, *async*,
*thread*, *timer*, and *main*.  The (crude) diagram below documents the
existing dependencies for these modules, showing the first level of
dependencies for each.  A ``.`` denotes that there are no further dependencies
(or the lower level dependencies are considered resolved)::

       weakref -> .
         utils -> .
      strutils -> .
      callable -> utils -> .
    nf_wrapper -> utils -> .
               -> callable -> .
          core -> utils -> .
               -> callable -> .
               -> nf_wrapper -> .
               -> [imports async at runtime]
         async -> utils -> .
               -> callable -> .
               -> core -> .
               -> [imports timer at runtime]
               -> [imports main at runtime]
        thread -> utils -> .
               -> callable -> .
               -> core -> .
               -> async -> .
         timer -> weakref -> .
               -> utils -> .
               -> nf_wrapper -> .
               -> core -> .
               -> thread -> .
          main -> nf_wrapper -> .
               -> core -> .
               -> timer -> .
               -> thread -> .

As the dependency graph shows, it is sufficient to import *main* to cause
the six "core" modules to be imported.  The *_LazyProxy* class in
``__init__.py`` will implicitly import *main* when almost any kaa object is
referenced, which should make it extremely unlikely that either *async* or
*main* should ever be imported for the first time within a thread.
