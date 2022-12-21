"""
Manual test for the context mangler.
"""

import pprint

import riscos.contextmangler as contextmangler


# FIXME: Make these tests better

def test():
    pprint.pprint(contextmangler.list_context_manglers())

    for mangler in contextmangler.list_context_manglers():
        print("Mangler {}:".format(mangler.name))

        context = mangler(0)
        for step in range(8):
            offset = context.offset
            assert(offset == step)
            print("  Step %i: opaque=%i (&%x) => offset=%i" % (step, context.opaque, context.opaque, offset))
            newcontext = mangler(context.opaque)
            assert(newcontext.offset == context.offset)
            context += 1


if __name__ == '__main__':
    test()
