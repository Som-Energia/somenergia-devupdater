#!/usr/bin/env python

import os
import sys
import subprocess
from contextlib import contextmanager
import time
import socket
import signal

def checkInVirtualEnvironment():
    venv = os.environ.get('VIRTUAL_ENV',None)
    if venv: return venv
    print(
        "\033[31;1m"
        "You need to use a virtual env, create it with mkvirtualenv\n"
        " $ mkvirtualenv -p $(which python2) --system-site-packages erp\n"
        " (erp)$ pip install yamlns consolemsg pathlib2 click\n"
        "\033[0m"
    )
    sys.exit(-1)

venv = checkInVirtualEnvironment()
print("Using venv: {}".format(os.path.basename(venv)))

try:
    from pathlib2 import Path
    import click
    from yamlns import namespace as ns
    from consolemsg import error, warn, step as _step, fail, success, color, printStdError, u
except ImportError:
    print(
        "\033[31;1m"
        "You need to manually install those use pip packages\n"
        " (erp)$ pip install yamlns consolemsg pathlib2 click\n"
        "\033[0m"
    )
    sys.exit(-1)


srcdir = Path(__file__).absolute().parent

progress = ns(steps=[])

def step(description, *args, **kwds):
    _step(description, *args, **kwds)
    progress.steps.append(ns(
        name=description.format(*args,**kwds),
        commands=[],
    ))

def running(command, *args, **kwds) :
    printStdError(color('35;1', "Running: "+command, *args, **kwds))
    if not progress.steps:
        step("Unnamed")
    progress.steps[-1].commands.append(ns(
        command=command.format(*args, **kwds),
    ))

def endrun(errorcode, outlines, errlines, mixlines):
    failed = errorcode != 0
    outlines, errlines, mixlines = (
        u''.join(l) for l in (outlines, errlines, mixlines))
    if failed:
        progress.steps[-1].commands[-1].update(
            failed = True,
            output = u''.join(mixlines)
        )

    return errorcode, outlines, errlines, mixlines


@contextmanager
def cd(path) :
    oldpath = os.getcwd()
    os.chdir(path)
    running("cd {}",os.getcwd())
    try:
        yield
    finally:
        os.chdir(oldpath)
        running("cd {}",os.getcwd())

@contextmanager
def background(command) :
    running("[Background] {}", command)
    process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid)
    try:
        yield process
    finally:
        running("Terminating: {}", command)
        os.killpg(os.getpgid(process.pid), signal.SIGHUP)
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait()

def baseRun(command, *args, **kwds):
    running(command, *args, **kwds)
    command = command.format(*args, **kwds)
    process = subprocess.Popen(command, shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        universal_newlines=True,
        )
    outlines = []
    errlines = []
    mixlines = []

    def doline(line, ostream, lines):
        if not line: return
        line = u(line)
        ostream.write(line)
        ostream.flush()
        lines.append(line)
        mixlines.append(line)

    import select
    poll = select.poll()
    poll.register(process.stdout.fileno(), select.POLLIN)
    poll.register(process.stderr.fileno(), select.POLLIN)

    while process.poll() is None:
        for fd, flags in poll.poll():
            if fd == process.stdout.fileno():
                doline(process.stdout.readline(), sys.stdout, outlines)
            if fd == process.stderr.fileno():
                doline(process.stderr.readline(), sys.stderr, errlines)
    doline(process.stdout.read(), sys.stdout, outlines)
    doline(process.stderr.read(), sys.stderr, errlines)

    return endrun(process.returncode, outlines, errlines, mixlines)


def captureOrFail(command, *args, **kwds):
    code, out, err, mix = baseRun(command, *args, **kwds)
    if code:
        error("Command failed with code {}: {}\n{}",
            code,
            command.format(*args, **kwds),
            err)
        fail("Exiting with failure")
    return out

def captureAndGo(command, *args, **kwds):
    code, out, err, mix = baseRun(command, *args, **kwds)
    if code:
        warn("Command failed with code {}: {}\n{}",
            code,
            command.format(*args, **kwds),
            mix)
    return out

def runOrFail(command, *args, **kwds):
    code, out, err, mix = baseRun(command, *args, **kwds)
    if code:
        error("Command failed with code {}: {}\n{}",
            code,
            command.format(*args, **kwds),
            err)
        fail("Exiting with failure")

def runTests(repo):
    errors = []
    for command in repo.tests:
        commandResult = ns(command=command)
        errors.append(commandResult)
        code, out, err, mix = baseRun(command)
        if code:
            error("Test failed: {}", command)
            commandResult.update(
                failed = True,
                errorcode=code,
                output = mix,
            )
    return errors

def testRepositories(p, results):

    results.failures=ns()
    for repo in p.repositories:
        if 'tests' not in repo: continue
        with cd(repo.path):
            result = runTests(repo)
            results.failures[repo.path] = result


def summary(results):
    print(results.dump())
    return ''.join((
        "- Failed module {module}\n".format(
            module=module,
            )
        for module in results.get('failures',[])
        if any(
            'failed' in command
            for command in results.failures[module]
        )
    ))

def hasChanges(results):
    return any(results.changes.values())

### Git stuff

def newCommitsFromRemote(repo):
    output = captureOrFail(
        #"git log HEAD..HEAD@{{upstream}} " # old version
        "git log ..origin/{branch} "
            " --pretty=format:'%h\t%ai\t%s'"
            .format(**repo))

    return [
        ns(
            id=id,
            date=date,
            subject=subject,
            )
        for id, date, subject in (
            line.split('\t')
            for line in output.splitlines()
        )
    ]

def rebase():
    errorcode, _,_, mix = baseRun("git rebase")
    if errorcode:
        error("Aborting failed rebase.\n{}",mix)
        runOrFail("git rebase --abort")

def fetch():
    runOrFail("git fetch --all")

def currentBranch():
    return captureOrFail("git rev-parse --abbrev-ref HEAD").strip()

def clone(repository):
    """
    The repository is a dict with the following keys:
    - path: the local path where to place it
    - url: remote url where to fetch it
    - branch: the working branch
    """
    step("Cloning repository {path}: {url}",**repository)
    if Path(repository.path).exists():
        warn("Path {path} already exists. Skipping clone", **repository)
        return
    runOrFail("git clone {url} {path} --branch {branch}",**repository)


def cloneOrUpdateRepositories(p, results):
    changes = results.setdefault('changes',ns())
    for repo in p.repositories:
        if not os.path.exists(repo.path):
            changes[repo.path] = [] # TODO: log cloned
            step("Cloning {path}", **repo)
            clone(repo)
            continue
        with cd(repo.path):
            step("Fetching changes {path}",**repo)
            fetch()
            branch = currentBranch()
            if branch != repo.branch:
                warn("Not rebasing repo '{path}': "
                    "in branch '{currentBranch}' instead of '{branch}'",
                    currentBranch=branch, **repo)
                continue
            repoChanges = newCommitsFromRemote(repo)
            if not repoChanges: continue
            changes[repo.path] = repoChanges
            step("Rebasing {path}",**repo)
            rebase()
    return changes


## Pip stuff

def installEditable(path):
    step("Install editable repository {}", path)
    with cd(path):
        runOrFail("pip install -e .")

def pipPackages():
    """
    Returns a list of namespaces, containing information
    on  installed packages:
    package name, current version, available version,
    type and optionally the editable path.
    """
    step("Optaining pip packages status")
    output = captureOrFail("pip list -o --exclude-editable --format=columns")
    lines = output.splitlines()
    return [
        ns(
            name=package,
            old=old,
            new=new,
            type=pkg,
            **ns(path=path) if path else ns()
        )
        for package, old, new, pkg, path in 
        (
            line.split()+['']*(5-len(line.split()))
            for line in lines[2:]
        )
    ]

def pendingPipUpgrades():
    "Returns a list of pip packages with available upgrades"
    from distutils.version import LooseVersion as version
    return [
        p
        for p in pipPackages()
        if version(p.old)<version(p.new)
        and ('path' not in p or not p.path)
        ]

def pipInstallUpgrade(packages, results):
    # TODO: notify as changes
    step("Upgrading pip packages: {}", ', '.join(packages))
    if not packages:
        warn("No pending pip upgrades")
        return

    changes = results.setdefault('changes',ns())

    packages = ' '.join(["'{}'".format(x) for x in packages])
    runOrFail('pip install --upgrade {}', packages)

def missingPipPackages(required):
    installed = [
        package.name
        for package in pipPackages()
    ]
    return [
        package
        for package in required
        if package not in installed
    ]

### Apt stuff


def aptInstall(packages):
    packages=' '.join(packages)
    step("Installing debian dependencies: {}",packages)
    runOrFail("sudo apt install {}", packages)

def missingAptPackages(packages):
    step("Checking missing debian packages")
    out = captureAndGo("dpkg-query -W  -f '${{package}}\\n' {}",
        " ".join(packages))
    present = out.split()
    return [p for p in packages if p not in present]

def installCustomPdfGenerator():
    step("Installing custom wkhtmltopdf")
    runOrFail("wget https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.2.1/wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    runOrFail("wget http://security.ubuntu.com/ubuntu/pool/main/libp/libpng/libpng12-0_1.2.54-1ubuntu1.1_amd64.deb")
    runOrFail("sudo dpkg -i libpng12-0_1.2.54-1ubuntu1.1_amd64.deb wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    runOrFail("rm libpng12-0_1.2.54-1ubuntu1.1_amd64.deb wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")


### Database stuff

def downloadLastBackup():
    backupfile = None
    if c.reuseBackup:
        for backupfile in sorted(Path(c.workingpath).glob('somenergia-*.sql.gz')):
            break
    if not backupfile:
        import datetime
        yesterday = format((datetime.datetime.now()-datetime.timedelta(days=1)).date())
        backupfile = Path("somenergia-{}.sql.gz".format(yesterday))

    if backupfile.exists() and not c.forceDownload:
        warn("Reusing already downloaded '{}'", backupfile)
        return backupfile

    runOrFail("scp somdevel@sf5.somenergia.coop:/var/backup/somenergia.sql.gz {}", backupfile)
    return backupfile

def dbExists(dbname):
    out = captureOrFail("""psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='{}'" """,
        dbname)
    return out.strip()=="1"

def loadDb(p):
        backupfile = downloadLastBackup()
        runOrFail("dropdb --if-exists {dbname}", **c)
        runOrFail("createdb {dbname}", **c)
        runOrFail("( pv -f {} | zcat | psql -e {dbname} ) 2>&1", backupfile, **c)
        runOrFail("""psql -d {dbname} -c "UPDATE res_partner_address SET email = '{email}'" """, **c)


def firstTimeSetup(p,c,results):
    somenergiaConf = Path(c.virtualenvdir)/'conf/erp.conf'
    if somenergiaConf.exists(): return

    createLogDir(p,c,results)
    generateErpConf(p,c,results)
    setupDBUsers(p,c,results)

def createLogDir(p,c,results):
    logdir = Path(c.virtualenvdir)/'var/log'
    logdir.mkdir(parents=True, exist_ok=True)

def generateErpRunner(p,c,results):
    "Generates an erp server runner based on the .in template"

    step("Generating Erp Runner")
    runner = Path(c.virtualenvdir) / 'bin/erpserver'
    runnerTemplate = srcdir / 'erpserver.in'
    content = runnerTemplate.read_text(encoding='utf8').format(**c)
    runner.write_text(content, encoding='utf8')
    runner.chmod(0o744)

def generateErpConf(p,c,results):
    "Generates an erp conf file based on the .in template"

    step("Generating Erp Configuration")
    somenergiaConf = Path(c.virtualenvdir)/'conf/erp.conf'
    somenergiaConf.parent.mkdir(parents=True, exist_ok=True)
    confTemplate = srcdir / 'erp.conf'
    confContent = confTemplate.read_text(encoding='utf8').format(**c)
    somenergiaConf.write_text(confContent, encoding='utf8')

def setupDBUsers(p,c,results):
    # This requires the following line on the sudoers
    # youruser  ALL = (postgres) /path/to/pgaduser.sh

    if c.systemUser not in p.postgresUsers:
        p.postgresUsers.append(c.systemUser)

    for user in p.postgresUsers:
        runOrFail("sudo -u postgres {}/pgadduser.sh {}", srcdir, user)

def isErpPortOpen():
    try:
        s = socket.create_connection(('localhost', c.erpport), timeout=4)
    except socket.error as ex:
        return False
    s.close()
    return True

def waitErpOpen():
    for i in range(c.erpStartupTimeout):
        if isErpPortOpen():
            return True
        time.sleep(1)
    return False

def deploy(p, results):
    if c.skipDeploy:
        warn("Deployment skipped")
        return

    missingApt = missingAptPackages(p.ubuntuDependencies)
    if missingApt:
        aptInstall(p.ubuntuDependencies)
    if missingAptPackages(['wkhtmltox']):
        installCustomPdfGenerator()

    if missingPipPackages(p.pipDependencies):
        pipInstallUpgrade(p.pipDependencies, results)
    elif not c.skipPipUpgrade:
        pipInstallUpgrade(pendingPipUpgrades(), results)

    cloneOrUpdateRepositories(p, results)

    if c.skipPipUpgrade:
        warn("Skiping pip editables install")
    else:
        # TODO: Just the ones updated or cloned
        for path in p.editablePackages:
            installEditable(path)

    # TODO: on deploy, add both gisce and som rolling remotes

    # TODO: Just a first time or if one repo is cloned
    with cd('erp'):
        runOrFail("./tools/link_addons.sh > /dev/null")

    firstTimeSetup(p,c,results)

    if dbExists(c.dbname) and c.keepDatabase:
        warn("Keeping existing database")
    else:
        loadDb(p)



def completeRepoData(repository):
    repository.setdefault('branch', 'master')
    repository.setdefault('user', 'gisce')
    repository.setdefault('url',
        'git@github.com:{user}/{path}.git'
        .format(**repository))

c = ns(
    workingpath='.',
    email='someone@somewhere.net',
    dbname='somenergia',
    pgversion='10',
    erpport=18069,
    skipPipUpgrade = True,
    forceTest = False,
    keepDatabase = False,
    forceDownload = False,
    reuseBackup = False,
    skipDeploy = False,
    skipErpUpdate = False,
    virtualenvdir = os.environ.get('VIRTUAL_ENV'),
    systemUser = os.environ.get('USER'),
    erpStartupTimeout = 30,
)
c.update(**ns.load("config.yaml"))


@click.command(help="Executes a build setup/update of the erp")
@click.option('--db','dbname',
    metavar='DATABASE',
    help='Name of the database',
    )
@click.option('--skipdeploy', 'skipDeploy',
    help='Skips initial deployment altogether',
    is_flag=True,
    )
@click.option('--skippip', 'skipPipUpgrade',
    help='Skips upgrading the pip packages',
    is_flag=True,
    )
@click.option('--keepdb', 'keepDatabase',
    help='Keeps the existing database unless it does not exist',
    is_flag=True,
    )
@click.option('--reusebackup', 'reuseBackup',
    help='Skips database backup download and reuses the last one',
    is_flag=True,
    )
@click.option('--forcedownload', 'forceDownload',
    help="Forces the database backup download even if a local copy exists already",
    is_flag=True,
    )
@click.option('--skiperpupdate', 'skipErpUpdate',
    help='Do not run update on erp modules to speedup execution when no modules have been updated',
    is_flag=True,
    )
def main(**kwds):
    c.update((k,v) for k,v in kwds.items() if v is not None)
    print(c.dump())
    results=ns(
        progress = progress,
    )

    p = ns.load("project.yaml")
    for repo in p.repositories:
        completeRepoData(repo)

    try:
        os.makedirs(c.workingpath)
    except OSError:
        pass

    with cd(c.workingpath):
        generateErpRunner(p,c,results)
        deploy(p, results)

        if not c.skipErpUpdate:
            runOrFail('erpserver --update=all --stop-after-init')

        if not c.forceTest and not hasChanges(results):
            raise Exception("No changes")

        if isErpPortOpen():
            fail("Another erp instance is using the port")

        with background('erpserver'):
            if not waitErpOpen():
                fail("Erp took more than {} seconds to startup"
                    .format(c.erpStartupTimeout))

            testRepositories(p, results)

    results.dump("results.yaml")
    print(summary(results))

    if results.failures:
        sys.exit(-1)



if __name__ == '__main__':
    main()



# vim: et ts=4 sw=4
