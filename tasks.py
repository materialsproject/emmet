from datetime import date
import re

from invoke import task

from emmet import __version__


@task
def setver(c):
    # Calendar versioning (https://calver.org/), with a patch segment
    # for release of multiple version in a day (should be rare).
    new_ver = date.today().isoformat().replace("-", ".")
    if __version__.startswith(new_ver):
        if __version__ == new_ver:
            new_ver += ".1"
        else:
            year, month, day, patch = new_ver.split('.')
            patch = str(int(patch) + 1)
            new_ver = ".".join(year, month, day, patch)
    with open("emmet/__init__.py", "r") as f:
        lines = [re.sub('__version__ = .+',
                        '__version__ = "{}"'.format(new_ver),
                        l.rstrip()) for l in f]
    with open("emmet/__init__.py", "w") as f:
        f.write("\n".join(lines))

    with open("setup.py", "r") as f:
        lines = [re.sub('version=([^,]+),',
                        'version="{}",'.format(new_ver),
                        l.rstrip()) for l in f]
    with open("setup.py", "w") as f:
        f.write("\n".join(lines))
    print("Bumped version to {}".format(new_ver))


@task
def publish(c):
    c.run("rm dist/*.*", warn=True)
    c.run("python setup.py sdist bdist_wheel")
    c.run("twine upload dist/*")
