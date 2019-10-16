#!/usr/bin/env python

import os
import sys

def checkInVirtualEnvironment():
    venv = os.environ.get('VIRTUAL_ENV',None)
    if venv: return venv
    print(
        "\033[31;1m"
        "You need to use a virtual env, create it with mkvirtualenv\n"
        " $ mkvirtualenv -p $(which python2) --system-site-packages erp\n"
        " (erp)$ pip install yamlns consolemsg\n"
        "\033[0m"
    )
    sys.exit(-1)

venv = checkInVirtualEnvironment()
print("Using venv: {}".format(os.path.basename(venv)))

import subprocess
from contextlib import contextmanager
from yamlns import namespace as ns
from consolemsg import step, error, warn, fail, success, color, printStdError

def running(command, *args, **kwds) :
    printStdError(color('35;1', "Running: "+command, *args, **kwds))

@contextmanager
def cd(path) :
    oldpath = os.getcwd()
    os.chdir(path)
    step("Entering {}",os.getcwd())
    try:
        yield
    finally:
        os.chdir(oldpath)
        #step("Back into {}",oldpath)

def run(command, *args, **kwds):
    running(command, *args, **kwds)
    command = command.format(*args, **kwds)
    try:
        output = subprocess.check_output(command, shell=True)
        return 0, output
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output

def runOrFail(command, *args, **kwds):
    err, output = run(command, *args, **kwds)
    if not err: return output
    fail(output)

def runTests(repo):
    errors = []
    for command in repo.tests:
        try:
            step("Running: {}", command)
            commandResult = ns(command=command)
            errors.append(commandResult)
            subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            error("Test failed: {}", command)
            commandResult.update(
                failed = True,
                errorcode=e.returncode,
                output = e.output,
            )
    return errors

# TODO: start/stopService

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

def newCommitsFromRemote():
    errorcode, output = run(
        "git log HEAD..HEAD@{{upstream}} "
            "--exit-code --pretty=format:'%h\t%ai\t%s'"
                )
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
    errorcode, output = run("git rebase")
    if errorcode:
        error("Aborting failed rebase.\n{}",output)
        run("git rebase --abort")

def fetch():
    errorcode, output = run(
        "git fetch --all")

def currentBranch():
    errorcode, output = run(
        "git rev-parse --abbrev-ref HEAD")
    # TODO: errors unmanaged
    return output.strip()

def clone(repository):
    """
    The repository is a dict with the following keys:
    - path: the local path where to place it
    - url: remote url where to fetch it
    - branch: the working branch
    """
    step("Cloning repository {path}: {url}",**repository)
    if os.path.exists(repository.path):
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
            repoChanges = newCommitsFromRemote()
            if not repoChanges: continue
            changes[repo.path] = repoChanges
            step("Rebasing {path}",**repo)
            rebase()
    return changes


## Pip stuff

def installEditable(path):
    step("Install editable repository {}", path)
    with cd(path):
        run("pip install -e .")

def pipPackages():
    """
    Returns a list of namespaces, containing information
    on  installed packages:
    package name, current version, available version,
    type and optionally the editable path.
    """

    err, output = run("pip list -o --exclude-editable --format=columns")
    if err:
        error("Failed to get list of pip packages")
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
    err, output = run('pip install --upgrade {}', packages)
    if err:
        error("Error upgrading pip packages")
        fail(output)

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
    er, out=run("sudo apt install {}", packages)
    if not er: return
    error("Unable to install debian packages:\n{}", out)

def missingAptPackages(packages):
    step("Checking missing debian packages")
    er, out = run("dpkg-query -W  -f '${{package}}\\n' {}",
        " ".join(packages))
    present = out.split()
    return [p for p in packages if p not in present]

def installCustomPdfGenerator():
    step("Installing custo wkhtmltopdf")
    run("wget https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.2.1/wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    run("wget http://security.ubuntu.com/ubuntu/pool/main/libp/libpng/libpng12-0_1.2.54-1ubuntu1.1_amd64.deb")
    run("sudo dpkg -i libpng12-0_1.2.54-1ubuntu1.1_amd64.deb wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    run("rm libpng12-0_1.2.54-1ubuntu1.1_amd64.deb wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")


### Database stuff

def downloadLastBackup(backupfile = None):
    if not backupfile:
        import datetime
        yesterday = format((datetime.datetime.now()-datetime.timedelta(days=1)).date())
        backupfile = "somenergia-{}.sql.gz".format(yesterday)

    if os.path.exists(backupfile):
        warn("Reusing already downloaded '{}'", backupfile)
        return backupfile

    runOrFail("scp somdevel@sf5.somenergia.coop:/var/backup/somenergia.sql.gz {}", backupfile)
    return backupfile

def dbExists(dbname):
    err, out = run("""psql -tAc "SELECT 1 FROM pg_database WHERE datname='{}'" """,
        dbname)
    return out.strip()=="1"

def loadDb(p):
        backupfile = downloadLastBackup()
        if dbExists(c.dbname):
            runOrFail("dropdb --if-exists {dbname}", **c)
        runOrFail("createdb {dbname}", **c)
        runOrFail("pv {} | zcat | psql -e {dbname}", backupfile, **c)
        runOrFail("""psql -d {dbname} -c "UPDATE res_partner_address SET email = '{email}'" """, **c)


def deploy(p, results):
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

    if not c.skipPipUpgrade:
        # TODO: Just the ones updated or cloned
        for path in p.editablePackages:
            installEditable(path)

    # TODO: on deploy, add both gisce and som rolling remotes

    # TODO: Just a first time or if one repo is cloned
    with cd('erp'):
        runOrFail("./tools/link_addons.sh")

    if not os.path.exists('{VIRTUAL_ENV}/conf/somenergia.conf'.format(**os.environ)):
        run('mkdir -p $VIRTUAL_ENV/conf')
        step("Next command will need somdevel@sf5 password")
        run('ssh somdevel@sf5.somenergia.coop -t "sudo -u erp cat /home/erp/conf/somenergia.conf" | tail -n +2 > $VIRTUAL_ENV/conf/somenergia.conf')

        systemUser = os.environ.get('USER')
        if systemUser not in p.postgresUsers:
            p.postgresUsers.append(systemUser)
        for user in p.postgresUsers:
            runOrFail("""sudo su -c 'echo "local all '{user}' peer" >> /etc/postgresql/*/main/pg_hba.conf'""", user=user, **c)
            runOrFail("sudo -u postgres createuser -P -s {}", user)

    if not dbExists(c.dbname) or c.updateDatabase:
        loadDb(p)

    if not c.forceTest and not hasChanges(results):
        raise Exception("No changes")



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
    pgversion='9.5',
    skipPipUpgrade = True,
    forceTest = False,
    updateDatabase = False,
)
c.update(**ns.load("config.yaml"))


def main():
    results=ns()
    p = ns.load("project.yaml")

    for repo in p.repositories:
        completeRepoData(repo)

    try:
        os.makedirs(c.workingpath)
    except OSError:
        pass

    with cd(c.workingpath):
        deploy(p, results)
        #testRepositories(p, results)


    results.dump("results.yaml")
    print summary(results)


if __name__ == '__main__':
    main()


# vim: et ts=4 sw=4
