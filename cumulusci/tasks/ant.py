import base64
import logging
import os
import sarge
import tempfile
import zipfile

from cumulusci.core.exceptions import AntTargetException
from cumulusci.core.exceptions import ApexTestException
from cumulusci.core.exceptions import DeploymentException
from cumulusci.core.tasks import BaseTask

CUMULUSCI_PATH = os.path.realpath(
    os.path.join(
        os.path.dirname(
            os.path.realpath(__file__),
        ),
        '..',
        '..'
    )
)

class BaseAntTask(BaseTask):
    name = 'BaseAntTask'

    task_options = {
        'target': {
            'description': 'The ant target to run',
            'required': True,
        },
        'verbose': {
            'description': 'The ant target to run',
            'required': False,
        }
    }

    def __init__(self, project_config, task_config, org_config, **kwargs):
        self.org_config = org_config
        self.options = kwargs
        super(BaseAntTask, self).__init__(project_config, task_config)

    def __call__(self):
        self._refresh_oauth_token()
        return self._run_task()

    def _run_task(self):
        target = self.task_config['options']['target']
        env = self._get_ant_env()
        return self._run_ant_target(target, env)

    def _get_ant_env(self):
        env = {
            'CUMULUSCI_PATH': CUMULUSCI_PATH,
            'CUMULUSCI_CLI': 'True',
            'PATH': os.environ.get('PATH'),
            'ANT_OPTS': '-Xmx512m',
            'SF_SESSIONID': self.org_config.access_token,
            'SF_SERVERURL': self.org_config.instance_url,
        }
        venv = os.environ.get('VIRTUAL_ENV')
        if venv:
            env['VIRTUAL_ENV'] = venv
        return env

    def _run_ant_target(self, target, env):
        verbose = self.options.get('verbose') in ('True','true')
            
        # Execute the command
        if verbose:
            cmd = 'ant %s' % target
        else:
            cmd = '%s/ci/ant_wrapper.sh %s' % (CUMULUSCI_PATH, target)
        p = sarge.Command(cmd, stdout=sarge.Capture(buffer_size=-1), env=env)
        p.run(async=True)
    
        # Print the stdout buffer until the command completes and capture all lines in log for reference in exceptions
        log = []
        while p.returncode is None:
            for line in p.stdout:
                log.append(line.rstrip())
                self.logger.info(line.rstrip())
            p.poll()
    
        # Check the return code, raise the appropriate exception if needed
        if p.returncode:
            logtxt = '\n'.join(log)
            try:
                if logtxt.find('All Component Failures:') != -1:
                    raise DeploymentException(logtxt)
                elif logtxt.find('[exec] Failing Tests') != -1:
                    raise ApexTestException(logtxt)
                else:
                    raise AntTargetException(logtxt)
            except DeploymentException as e:
                self.logger.error('BUILD FAILED: One or more deployment errors occurred')
                raise e
            except ApexTestException as e:
                self.logger.error('BUILD FAILED: One or more Apex tests failed')
                raise e
            except AntTargetException as e:
                self.logger.error('BUILD FAILED: One or more Ant target errors occurred')
                raise e
        return p
            
    
    def _refresh_oauth_token(self):
        self.org_config.refresh_oauth_token(self.project_config.keychain.get_connected_app())
