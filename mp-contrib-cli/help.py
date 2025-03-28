from click.core import Command, Context, Group

from mp_contrib.cli.entry_point import mp_contrib


def recursive_help(cmd, parent=None):
    ctx = Context(cmd, info_name=cmd.name, parent=parent)
    print("```")
    print(cmd.get_help(ctx))
    print("```")
    commands = getattr(cmd, "commands", {})
    for sub in commands.values():
        if isinstance(sub, Group):
            print("## " + sub.name)
        elif isinstance(sub, Command):
            print("### " + sub.name)
        recursive_help(sub, ctx)


print("# MP Contrib Command Line Interface")
recursive_help(mp_contrib)
