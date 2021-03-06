#!/usr/bin/env python

import os
import sys
import subprocess
from contextlib import contextmanager
import time
import socket
import signal
import datetime

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

progress = ns(stages=[])

def currentStage():
    if not progress.stages:
        stage("Init")
    return progress.stages[-1]

def currentStep():
    if not currentStage().steps:
        step("Init")
    return currentStage().steps[-1]

def currentCommand():
    return currentStep().commands[-1]

def stage(description, *args, **kwds):
    printStdError(color('34;1', "Stage: "+description, *args, **kwds))
    progress.stages.append(ns(
        name=description.format(*args,**kwds),
        steps=[],
    ))

def step(description, *args, **kwds):
    _step(description, *args, **kwds)
    currentStage().steps.append(ns(
        name=description.format(*args,**kwds),
        commands=[],
    ))

def running(command, *args, **kwds) :
    printStdError(color('35;1', "Running: "+command, *args, **kwds))
    currentStep().commands.append(ns(
        command=command.format(*args, **kwds),
        startTime=datetime.datetime.now(),
    ))

def endrun(errorcode, outlines, errlines, mixlines):
    failed = errorcode != 0
    outlines, errlines, mixlines = (
        u''.join(l) for l in (outlines, errlines, mixlines))
    terminationTime = datetime.datetime.now()
    ellapsedSeconds = (terminationTime - currentCommand().startTime).seconds
    currentCommand().update(
        ellapsedSeconds=ellapsedSeconds,
    )
    if failed:
        currentCommand().update(
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
            if not (flags & select.POLLIN):
                continue
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
        step("Testing {}", repo.path)
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


def fetchOrCloneRepository(repo):
    if not os.path.exists(repo.path):
        step("Cloning {path}", **repo)
        clone(repo)
        return repo.path, ['Cloned']
    step("Fetching changes {path}",**repo)
    with cd(repo.path):
        fetch()
        branch = currentBranch()
        if branch != repo.branch:
            warn("Not rebasing repo '{path}': "
                "in branch '{currentBranch}' instead of '{branch}'",
                currentBranch=branch, **repo)
            return repo.path, []
        repoChanges = newCommitsFromRemote(repo)
        return repo.path, repoChanges


def cloneOrUpdateRepositories(p, results):
    if c.fetchingProcesses>1:
        warn("Repos will be fetched {} at a time to speedup, expect mixed output".format(c.fetchingProcesses))
        from multiprocessing import Pool
        changes = results.setdefault('changes',ns())
        workers = Pool(c.fetchingProcesses)
        changes.update(
            (path, pathchanges)
            for path,pathchanges in workers.imap_unordered(fetchOrCloneRepository, p.repositories)
            if pathchanges)
        warn("End of mixed repos fetch")
        workers.close()
        return
    for repo in p.repositories:
        fetchOrCloneRepository(repo)

def rebaseRepositories(p, results):
    changes = results.setdefault('changes',ns())
    for repo in p.repositories:
        if not os.path.exists(repo.path):
            raise Exception("Repo {} missing")
        step("Updating repo {path}",**repo)
        with cd(repo.path):
            branch = currentBranch()
            if branch != repo.branch:
                warn("Not rebasing repo '{path}': "
                    "in branch '{currentBranch}' instead of '{branch}'",
                    currentBranch=branch, **repo)
                continue
            if not changes.get(repo.path, None):
                warn("No changes detected")
                continue
            step("Rebasing {path}",**repo)
            rebase()


## Pip stuff

def installEditable(path):
    step("Install editable repository {}", path)
    with cd(path):
        runOrFail("pip install -e .")

def missingPipRequirements(required):
    # TODO: should use pip installed packaging, no pkg_resources private copy
    from pkg_resources._vendor.packaging.utils import canonicalize_name as canon
    from pkg_resources._vendor.packaging.requirements import Requirement
    import pkg_resources
    installedVersions = dict(
        (canon(p.key), p.parsed_version)
        for p in pkg_resources.working_set
    )
    return [
        str(r)
        for r in (Requirement(p) for p in required)
        if canon(r.name) not in installedVersions
        or installedVersions[canon(r.name)] not in r.specifier
    ]

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
        and not p.get('path', None)
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

### Apt stuff


def aptInstall(packages):
    packages=' '.join(packages)
    step("Installing missing debian dependencies: {}",packages)
    runOrFail("sudo apt install -y {}", packages)

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
    yesterday = format((datetime.datetime.now()-datetime.timedelta(days=1)).date())

    if c.reuseBackup:
        for backupfile in sorted(Path(c.workingpath).glob('somenergia-*.sql.gz')):
            break

    if not backupfile:
        backupfile = Path("somenergia-{}.sql.gz".format(yesterday))

    if backupfile.exists() and not c.forceDownload:
        warn("Reusing already downloaded '{}'", backupfile)
        return backupfile

    remotefile = Path("/mnt/backups/postgres/sp2.{:%Y%m%d}.sql.gz".format(yesterday))
    runOrFail("scp somdevel@sp2:{} {}", remotefile, backupfile)
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
        runOrFail("{workingpath}/somenergia-utils/enable_destructive_tests.py --i-am-sure",**c)


def firstTimeSetup(p,c,results):
    createLogDir(p,c,results)
    setupDBUsers(p,c,results)
    generateErpRunner(p,c,results)
    generateErpConf(p,c,results)

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
    stage("Deploy")
    if c.skipDeploy:
        warn("Deployment skipped")
        return

    missingApt = missingAptPackages(p.ubuntuDependencies)
    if missingApt:
        aptInstall(p.ubuntuDependencies)
    if missingAptPackages(['wkhtmltox']):
        installCustomPdfGenerator()

    missingPip = missingPipRequirements(p.pipDependencies)
    if missingPip:
        warn("Missing pip packages: {}", missingPip)
        pipInstallUpgrade(missingPip, results)

    if c.upgradePipPackages:
        pipInstallUpgrade(pendingPipUpgrades(), results)

    # TODO: on deploy, add both gisce and som rolling remotes

    cloneOrUpdateRepositories(p, results)

    if not hasChanges(results) and not c.runUnchanged:
        warn("No changes detected, exiting")
        return

    rebaseRepositories(p, results)

    if c.skipPipUpgrade:
        warn("Skiping pip editables install")
    else:
        # TODO: Just the ones updated or cloned
        for path in p.editablePackages:
            installEditable(path)

    # TODO: Just a first time or if one repo is cloned
    with cd('erp'):
        runOrFail("./tools/link_addons.sh > /dev/null")

    somenergiaConf = Path(c.virtualenvdir)/'conf/erp.conf'
    if not somenergiaConf.exists():
        firstTimeSetup(p,c,results)

    if dbExists(c.dbname) and c.keepDatabase:
        warn("Keeping existing database")
    else:
        loadDb(p)


def dumpTestfarmData(p,results):
    if not c.get('testfarmDataDir'):
        return

    executionFile = Path(c.testfarmDataDir) / '{execution}-execution.yaml'.format(**results)
    results.dump(str(executionFile))

    # Stages that report each step
    detailedStages = p.get('detailedStages',[])
    ignoredStages = p.get('ignoredStages',[])

    now = '{:%Y/%m/%d %H:%M:%S}'.format(datetime.datetime.now())

    report = ns(
        project = "SomEnergia",
        lastupdate = now,
        clients = [],
    )

    def client(name, failedTasks, currentTask=''):
        report.clients.append(ns(
            name = name,
            status='red' if failedTasks else 'green',
            doing='run' if currentTask else 'wait', # also could be 'old'
            lastupdate = now,
            failedTasks = failedTasks,
            currentTask = currentTask,
        ))

    for stage in results.progress.stages:
        if stage.name in ignoredStages:
            continue

        if stage.name in detailedStages:
            failures = []
            for step in stage.steps:
                failures = [
                    command.command
                    for command in step.commands
                    if 'failed' in command
                ]
                client(
                    name=step.name,
                    failedTasks=failures,
                )
            continue

        failures = [
            step.name
            for step in stage.steps
            if any(
                'failed' in command
                for command in step.commands
            )
        ]
        client(
            name=stage.name,
            failedTasks=failures,
        )

    import json
    jsondata = json.dumps(report,
        indent=4,
        sort_keys=True,
        )
    outputfile=Path(c.testfarmDataDir)/'testfarm-data.js'
    outputfile.write_bytes(jsondata)



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
    erpport=18069,
    skipPipUpgrade = True,
    runUnchanged = False,
    keepDatabase = False,
    forceDownload = False,
    reuseBackup = False,
    skipDeploy = False,
    skipErpUpdate = False,
    virtualenvdir = os.environ.get('VIRTUAL_ENV'),
    systemUser = os.environ.get('USER'),
    erpStartupTimeout = 30,
    fetchingProcesses = 10,
    upgradePipPackages=False,
)
c.update(**ns.load("config.yaml"))


@click.command(help="Executes a build setup/update of the erp")
@click.option('--execname','name',
    metavar='EXECNAME',
    help='Execution name',
    )
@click.option('--db','dbname',
    metavar='DATABASE',
    help='Name of the database',
    )
@click.option('--skipdeploy', 'skipDeploy',
    help='Skips initial deployment altogether',
    is_flag=True,
    default=None,
    )
@click.option('--skippip', 'skipPipUpgrade',
    help='Skips upgrading the pip packages',
    is_flag=True,
    default=None,
    )
@click.option('--keepdb', 'keepDatabase',
    help='Keeps the existing database unless it does not exist',
    is_flag=True,
    default=None,
    )
@click.option('--reusebackup', 'reuseBackup',
    help='Skips database backup download and reuses the last one',
    is_flag=True,
    default=None,
    )
@click.option('--forcedownload', 'forceDownload',
    help="Forces the database backup download even if a local copy exists already",
    is_flag=True,
    default=None,
    )
@click.option('--skiperpupdate', 'skipErpUpdate',
    help='Do not run update on erp modules to speedup execution when no modules have been updated',
    is_flag=True,
    default=None,
    )
@click.option('--upgradepip', 'upgradePipPackages',
    help='Upgrade any pip package with a newer but compatible version available',
    is_flag=True,
    default=None,
    )
@click.option('--rununchanged', 'runUnchanged',
    help='Proceed even if no changes are detected in repositories',
    is_flag=True,
    default=None,
    )
def main(**kwds):
    c.update((k,v) for k,v in kwds.items() if v is not None)
    print(c.dump())

    now = "{:%Y%m%d-%H%M%S}".format(datetime.datetime.utcnow())

    results=ns(
        execution = c.get('execname', now),
        startDate = now,
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
        try:
            deploy(p, results)
        finally:
            results.dump("results.yaml")
            #print(summary(results))
            dumpTestfarmData(p,results)

            if results.get('failures', None):
                sys.exit(-1)

        if not c.runUnchanged and not hasChanges(results):
            error("No changes detected, run with --rununchanged to proceed anyway")
            sys.exit(0)

        try:
            stage("Testing")
            if not c.skipErpUpdate:
                step("Update Server")
                runOrFail('erpserver --update=all --stop-after-init --logfile=""')

            if isErpPortOpen():
                fail("Another erp instance is using the port")

            step("Server startup")
            with background('erpserver'):
                if not waitErpOpen():
                    fail("Erp took more than {} seconds to startup"
                        .format(c.erpStartupTimeout))

                testRepositories(p, results)
        finally:
            results.dump("results.yaml")
            #print(summary(results))
            dumpTestfarmData(p,results)

            if results.get('failures', None):
                sys.exit(-1)



if __name__ == '__main__':
    main()



# vim: et ts=4 sw=4
