"""
Context manipulation for a happier life.

'Opaque values' or 'contexts' are used in a number of RISC OS interfaces. They are
generally described as having no interpretation other than for the values 0 and -1,
which usually mean 'start' and 'end' respectively.

However, sometimes people have relied on them. That's bad because they will fall
foul of an interface which does truely treat them as opaque and give them random
values.

Most commonly the opaque value has been implemented as an incrementing value from
0. The RISC OS filesystem enumeration does this for some of the filesystems, notably
FileCore. It doesn't have to be that way. Some clients return pointers to areas of
memory.

A similar manglement is used by the WindowManager to return window handles so that
they retain certain invariants but continue to work in high memory, although that
is based on memory addresses rather than enumeration offsets.

The ContextMangler classes here will take a value, as seen by RISC OS, and convert
it to an actual offset for use internally. And they allow the context to be converted
back to the external form.

These manglers can be used by parts of RISC OS Pyromaniac to give contexts that
do not follow strictly incrementing values.
"""

try:
    from pyromaniac.config import ConfigurationError
except ImportError:
    # Outside of Pyromaniac we just use a ValueError
    ConfigurationError = ValueError


# A list of the mangler objects
manglers = {}


def register_context_mangler(mangler):
    """
    Register a context mangler, as a decorator.
    """
    name = mangler.name
    if not name:
        name = mangler.__name__
        mangler.name = name
        if name[:14] == 'ContextMangler':
            name = name[14:]
    manglers[name.lower()] = mangler

    return mangler


def find_context_mangler(name):
    """
    Find a context mangler, given a name.
    """
    mangler = manglers.get(name.lower(), None)
    if not mangler:
        raise ValueError("Context mangler '{}' is not known".format(name))
    return mangler


def create_context_mangler(name, opaque, *args):
    """
    Find a context mangler, given a name, then construct it, given some arguments.
    """
    mangler = find_context_mangler(name)
    return mangler(opaque, *args)


def list_context_manglers():
    """
    List all the context mangler classes.
    """
    return sorted(manglers.values(), key=lambda mangler: mangler.name)


def ContextManglerName(value):
    """
    Validate a ContextManglerName.

    Used by Pyromaniac for its configuration.
    """
    if value in manglers:
        return value
    raise ConfigurationError("Context mangler '{}' is not valid. Known manglers: {}".format(value,
                                                                                            ', '.join(sorted(manglers))))
ContextManglerName.help = "'identity' or one of the other mangler names"


class ContextManglerBase(object):
    """
    Make the context value the user sees more weird than usual - base implementation

    Both 0 and -1 are always the values 0 and -1.
    """

    # Override for the mangler name (otherwise derived from the class name)
    name = None

    # Description of the parameters to these objects
    params = []

    def __init__(self, context, *args):
        if context == 0:
            self.offset = 0
        elif context in (-1, 0xFFFFFFFF):
            self.offset = -1
        else:
            if context < 0:
                context = context + (1<<32)
            self.offset = self.unmangle(context)

    def __repr__(self):
        opaque = self.opaque
        return "<{}(opaque={} (&{}), offset={})>".format(self.__class__.__name__,
                                                         opaque, opaque, self.offset)

    def __iadd__(self, value):
        if self.offset == -1:
            # You cannot move from the terminal state.
            return self
        self.offset += value
        return self

    def finish(self):
        self.offset = -1

    @property
    def opaque(self):
        if self.offset in (0, -1):
            return self.offset
        return self.mangle(self.offset)

    def mangle(self, offset):
        """
        Turn an offset into an opaque value.
        """
        raise NotImplementedError("{}.mangle is not implemented".format(self.__class__.__name__))

    def unmangle(self, context):
        """
        Turn an opaque value into an offset.
        """
        raise NotImplementedError("{}.unmangle is not implemented".format(self.__class__.__name__))


@register_context_mangler
class ContextManglerIdentity(ContextManglerBase):
    """
    The number seen externally is the same as the offset - an identity transform.
    """

    def mangle(self, offset):
        return offset

    def unmangle(self, context):
        return context


@register_context_mangler
class ContextManglerBiased(ContextManglerBase):
    """
    Start the context at a base value.
    """
    params = ['Bias value to add to the opaque context']
    base = 0x76543

    def __init__(self, context, *args):
        if args:
            self.base = int(args[0])
            args = args[1:]
        super(ContextManglerBiased, self).__init__(context, args)

    def mangle(self, offset):
        return offset + self.base

    def unmangle(self, context):
        if context > 0 and context < self.base:
            raise ValueError("Invalid context value {} for biased mangler".format(context))
        return context - self.base


@register_context_mangler
class ContextManglerEOR(ContextManglerBase):
    """
    Perform an exclusive-OR of the context, biased from 1 so we never actually return 0.
    """
    params = ['EOR value to invert bits in the opaque context']
    # We also add 1 so that if we don't accidentally return 0.
    eor = 0x76543

    def __init__(self, context, *args):
        if args:
            self.eor = int(args[0])
            args = args[1:]
        super(ContextManglerEOR, self).__init__(context, args)

    def mangle(self, offset):
        return 1 + (offset ^ self.eor)

    def unmangle(self, context):
        return (context - 1) ^ self.eor


@register_context_mangler
class ContextManglerReverse(ContextManglerBase):
    """
    Reverse a number of bits (top to bottom).
    """
    params = ['Number of bits to reverse in the opaque context']
    # The number of bits to reverse - everything above that is preserved
    nbits = 17

    def __init__(self, context, *args):
        if args:
            self.nbits = int(args[0])
            args = args[1:]
        super(ContextManglerReverse, self).__init__(context, args)

    def mangle(self, offset):
        value = 0
        for n in range(self.nbits):
            value = value << 1
            if offset & 1:
                value |= 1
            offset = offset >> 1
        value = value | (offset << self.nbits)
        return value

    def unmangle(self, context):
        # This is the same in both directions
        return self.mangle(context)


@register_context_mangler
class ContextManglerDescending(ContextManglerBase):
    """
    Make the context value descend rather than ascend.
    """
    params = ['Value from which the opaque value will descend']
    # We also bias by 1 so that we don't hit 0.
    limit = 0x76543

    def __init__(self, context, *args):
        if args:
            self.limit = int(args[0])
            args = args[1:]
        super(ContextManglerDescending, self).__init__(context, args)

    def mangle(self, offset):
        low = offset % self.limit
        high = int(offset / self.limit) * self.limit
        low = self.limit - low
        return low + high + 1

    def unmangle(self, context):
        context = context - 1
        low = context % self.limit
        high = int(context / self.limit) * self.limit
        low = self.limit - low
        return low + high


@register_context_mangler
class ContextManglerMultiplier(ContextManglerBase):
    """
    Use the context value as a multiple of values, as you might have if they were stored in memory.
    """
    params = ['Multiplier for each offset',
              'Base value to add to opaque value']
    # Biased by an address base
    bias = 0x3800000
    # 24 bytes probably isn't unreasonable
    multiplier = 24

    def __init__(self, context, *args):
        if args:
            self.multiplier = int(args[0])
            args = args[1:]
        if args:
            self.bias = int(args[0])
            args = args[1:]
        super(ContextManglerMultiplier, self).__init__(context, args)

    def mangle(self, offset):
        return self.bias + offset * self.multiplier

    def unmangle(self, context):
        context -= self.bias
        if context < 0 or context % self.multiplier != 0:
            # This is an invalid context, so we return the terminal context.
            raise ValueError("Invalid context value {} for multiplier mangler".format(context))
        return int(context / self.multiplier)
