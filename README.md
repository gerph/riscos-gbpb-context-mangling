# RISC OS OS_GBPB context mangling code

This repository holds the context mangling code used by RISC OS Pyromaniac
to perturb applications which call `OS_GBPB`.

## Rationale

Under RISC OS, the calls `OS_GBPB` 9 to 12 are used to enumerate the
files in a directory. It may be called many times and in these cases it
is expected that a context value returned from the prior call will be
passed back, to indicate the offset at which the enumeration should
continue.

The value 0 is used to start, and the value -1 indicates that the
enumeration has completed. However, the offset is actually an internal
value which has no meaning to the application. It cannot assume that
the offset will increase, or that it will do so by any given value.
This can be exploited by filesystems by returning either a direct
pointer in memory to the internal directory entry, or could be ordered
oddly because the filesystem returned entries in a different order
than they were stored on disc.

Whatever the reasons, it is not guaranteed that the context be
monotonically incrementing - it is an opaque value. Applications which
assume otherwise will fail at some point.

RISC OS Pyromaniac is intended for debugging and testing code,
and has many features to allow this. The configuration for the
filesystem now allows the context values returned to be 'mangled'
from the offset that is used internally. The external interface to
the application remains the same, and the internal offset remains
the same, but the context value can be changed in different ways -
which will hopefully show up problematic code.

## Usage

Internally in RISC OS Pyromaniac these classes are wired into the
filesystem code with a method that looks like this:

```python
def enumeration_context(self, opaque):
    """
    Create an enumeration context object, using the supplied opaque value.

    Uses the configuration `filesystem.enumeration_context`.

    @param opaque:  The opaque value supplied by the user.
    """
    contextconfig = self.config.enumerate_context
    context = riscos.contextmangler.create_context_mangler(contextconfig, opaque)
    return context
```

Within the OS_GBPB code we initialise the context object with:

```python
try:
    context = ro.kernel.filesystem.enumeration_context(regs[4])
except ValueError:
    # If this isn't a valid value, we're going to assume it's the end
    if ro.kernel.filesystem.debug_osfileentries:
        print("Read direntries (GBPB %i) on '%s' context &%x, count %i: invalid context" % (reason, dirname, regs[4], ntoread))
    # FIXME: Raise a warning through trace?
    regs[3] = 0
    regs[4] = -1
    regs.cpsr_c = False
    return
```

and then for each iteration of the files we increment the context:

```python
context += 1
```

Finally at the end of the enumeration process we update the registers
with the new opaque context value:

```python
regs[4] = context.opaque
```

## Local tests

A simple manual test is provided which steps through the offsets, printing
out the context's opaque value and checking that it matches the expectations.

Within RISC OS Pyromaniac integration tests exercise the OS_GBPB interface
with different configurations to check that we are still enumerating all
the files.

