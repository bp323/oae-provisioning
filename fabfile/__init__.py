import os.path
import puppet
import slapchop

from fabric.api import *

env.disable_known_hosts = True
env.timeout = 10
env.connection_attempts = 6


@task
def ulous(environment):
    """Bootstrap and completely provision an OAE environment"""
    slapchop.bootstrap(environment=environment, yes=True)
    slapchop.fabric_setup(environment=environment)
    execute(internal_provision_puppet, environment=environment, hosts=[env.puppet_host])
    internal_provision_machines(environment=environment, puppet_ip=env.puppet_internal_ip)


@task
def provision_puppet(environment):
    """Bootstrap and provision the puppet machine for the specified environment"""
    slapchop.bootstrap(environment=environment, machine_names=['puppet'], yes=True)
    slapchop.fabric_setup(environment=environment)
    execute(internal_provision_puppet, environment=environment, hosts=[env.puppet_host])


@task
def provision_machines(environment, machine_names=None):
    """Bootstrap and provision the specified machines (by name) for the specified environment"""
    machine_names = slapchop.to_machine_array(machine_names)
    slapchop.bootstrap(environment=environment, machine_names=machine_names, yes=True)
    slapchop.fabric_setup(environment=environment)
    internal_provision_machines(environment=environment, machine_names=machine_names, puppet_ip=env.puppet_internal_ip)


@task
def internal_provision_puppet(environment):

    # Put the provision scripts on the remote server
    put('scripts/puppet-beforereboot.sh', 'puppet-beforereboot.sh', mode=0755)
    put('scripts/puppet-afterreboot.sh', 'puppet-afterreboot.sh', mode=0755)

    # Run the before reboot, reboot, then the after reboot
    run('./puppet-beforereboot.sh')
    slapchop.reboot(environment=environment, machine_names=['puppet'], yes=True)

    print 'Running puppet provisioning script. This will take some time and be silent. Hang in there.'
    run('./puppet-afterreboot.sh %s' % environment)

    # Download Java
    print 'Downloading jdk6 on to the puppet machine. This will take some time and be silent. Hang in there.'
    with cd('/etc/puppet/puppet-hilary/modules/oracle-java/files'):
        run('wget https://s3.amazonaws.com/oae-performance-files/jdk-6u45-linux-x64.bin')

    # Place the common_hiera_secure if one is specified
    hiera_secure_path = '%s/common_hiera_secure.json' % environment
    if (os.path.exists(hiera_secure_path)):
        put(hiera_secure_path, '/etc/puppet/puppet-hilary/environments/%s/hiera/common_hiera_secure.json' % environment)


@task
def internal_provision_machines(environment, puppet_ip, machine_names=None):
    for provision_group in env.provision_groups:
        # Only provision the machines we specified
        if machine_names != None:
            filtered_provision_group = {'hosts': [], 'names': []}
            for idx, name in enumerate(provision_group['names']):
                if machine_names == name or name in machine_names:
                    filtered_provision_group['names'].append(name)
                    filtered_provision_group['hosts'].append(provision_group['hosts'][idx])
            provision_group = filtered_provision_group

        # Only provision if anything was left in this array
        if (len(provision_group['names']) > 0):
            execute(internal_provision_machine, environment=environment, puppet_ip=puppet_ip, provision_group=provision_group, hosts=provision_group['hosts'])
            slapchop.reboot(environment=environment, machine_names=provision_group['names'], yes=True)
            execute(puppet.run, hosts=provision_group['hosts'])

            # Rebooting again will help pick up service or OS configuration changes that puppet performed that require restarts
            slapchop.reboot(environment=environment, machine_names=provision_group['names'], yes=True)


@task
@parallel
def internal_provision_machine(environment, puppet_ip, provision_group):
    name = provision_group['names'][provision_group['hosts'].index(env.host_string)]
    put('scripts/ubuntu.sh', 'ubuntu.sh', mode=0755)

    print 'Running machine provisioning script. This will take some time and be silent. Hang in there.'
    run('./ubuntu.sh %s %s %s' % (environment, name, puppet_ip))
