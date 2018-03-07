#!/usr/bin/env python

import os
import sys

def checkInVirtualEnvironment():
    venv = os.environ.get('VIRTUAL_ENV',None)
    if venv:
        print("Using venv: {}".format(os.path.basename(venv)))
    else:
        print(
            "You need to use a virtual env, create it with mkvirtualenv\n"
            " $ mkvirtualenv -p $(which python2) --system-site-packages erp\n"
            " (erp)$ pip install yamlns consolemsg\n"
        )
        sys.exit(-1)

checkInVirtualEnvironment()


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


def downloadLastBackup(backupfile = None):
    if not backupfile:
        import datetime
        yesterday = format((datetime.datetime.now()-datetime.timedelta(days=1)).date())
        backupfile = "somenergia-{}.sql.gz".format(yesterday)

    if os.path.exists(backupfile):
        warn("Reusing already downloaded '{}'", backupfile)

    runOrFail("scp somdevel@sf5.somenergia.coop:/var/backup/somenergia.sql.gz {}", backupfile)
    return backupfile

def newCommitsFromRemote():
    errorcode, output = run(
        "git log HEAD..ORIG_HEAD "
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


def hasChanges(results):
    return any(results.changes.values())

def update(p, results, force):

    results.changes = ns()
    for repo in p.repositories:
        with cd(repo.path):
            step("Fetching changes {path}",**repo)
            fetch()
            changes = newCommitsFromRemote()
            if not changes: continue
            results.changes[repo.path] = newCommitsFromRemote()

    if not force and not hasChanges(results):
        raise Exception("No changes")

    for repo in p.repositories:
        if os.path.exists(repo.path):
            with cd(repo.path):
                step("Rebasing {path}",**repo)
                rebase()
        else:
            step("Cloning {path}", **repo)
            clone(repo)
    return results

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
        for module in results.failures
        if any(
            'failed' in command
            for command in results.failures[module]
        )
    ))

def pipPackages():
    err, output = run("pip list -o --format=columns")
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
    from distutils.version import LooseVersion as version
    return [
        p for p in pipPackages()
        if version(p.old)<version(p.new)
        and ('path' not in p or not p.path)
        ]

def pipInstallUpgrade(packages):
    # TODO: notify as changes
    step("Upgrading pip packages: {}", ', '.join(packages))
    if not packages:
        warn("No pending pip upgrades")
        return

    packages = ' '.join(["'{}'".format(x) for x in packages])
    err, output = run('pip install --upgrade {}', packages)
    if err:
        error("Error upgrading pip packages")
        fail(output)

def aptInstall(packages):
    packages=' '.join(packages)
    step("Installing debian dependencies: {}",packages)
    er, out=run("sudo apt-get install {}", packages)
    if not er: return
    error("Unable to install debian packages:\n{}", out)

def installCustomPdfGenerator():
    step("Installing custo wkhtmltopdf")
    run("wget https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.2.1/wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    run("sudo dpkg -i wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")
    run("rm wkhtmltox-0.12.2.1_linux-trusty-amd64.deb")

def deploy(p):
    False and aptInstall(p.ubuntuDependencies)
    False and installCustomPdfGenerator()
    False and pipInstallUpgrade(p.pipDependencies)
    for repository in p.repositories:
        clone(repository)

    for path in p.editablePackages:
        False and installEditable(path)

    # TODO: on deploy, add both gisce and som rolling remotes

    with cd('erp'):
        runOrFail("./tools/link_addons.sh")

    run('mkdir -p $VIRTUAL_ENV/conf')

    # TODO: Copy configuration
    # run('ssh somdevel@sf5.somenergia.coop -t "sudo -u erp cat /home/erp/conf/somenergia.conf" | tail -n +2 > $VIRTUAL_ENV/conf/somenergia.conf')

    systemUser = os.environ.get('USER')
    p.postgresUsers.append(systemUser)
    for user in p.postgresUsers:
        # TODO: Postgres version in config path!!
        False and runOrFail("""sudo su -c 'echo "local all '{user}' peer" >> /etc/postgresql/{pgversion}/main/pg_hba.conf'""", user=user, **c)
        False and runOrFail("sudo -u postgres createuser -P -s {}", user)

    backupfile = downloadLastBackup()

    run("createdb {dbname}", **c)
    run("zcat {} | psql -e {dbname}", backupfile, **c)
    run("""psql -d {dbname} -c "UPDATE res_partner_address SET email = '{email}'" """, **c)


def completeRepoData(repository):
    repository.setdefault('branch', 'master')
    repository.setdefault('user', 'gisce')
    repository.setdefault('url',
        'git@github.com:{user}/{path}.git'
        .format(**repository))


def clone(repository):
    completeRepoData(repository)
    step("Cloning repository {path}: {url}",**repository)
    if os.path.exists(repository.path):
        warn("Path {path} already exists. Skipping clone", **repository)
        return
    runOrFail("git clone {url} {path} --branch {branch}",**repository)

def installEditable(path):
    step("Install editable repository {}", path)
    with cd(path):
        run("pip install -e .")

results=ns()
p = ns.load("project.yaml")
c = ns.load("config.yaml")
try:
    os.makedirs(c.workingpath)
except OSError:
    pass

with cd(c.workingpath):
    deploy(p)
    #update(p, results, force=True)
    #testRepositories(p, results)
    #print(ns(packages=pendingPipUpgrades()).dump())
    #pipInstallUpgrade(pendingPipUpgrades())


results.dump("results.yaml")
print summary(results)





# vim: et ts=4 sw=4
