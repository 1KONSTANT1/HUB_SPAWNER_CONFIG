from enum import Enum
import batchspawner
c = get_config()

#настройки логгирования
c.JupyterHub.log_level = 'DEBUG'
c.JupyterHub.extra_log_file = '/var/log/jupyterhub.log'

#не беспокоиться о небезопасном подключении
c.JupyterHub.confirm_no_ssl = True


c.JupyterHub.port = 8888 #Порт где работает JupyterHUB
c.JupyterHub.hub_ip = '0.0.0.0'  # Hub слушает на всех интерфейсах
c.JupyterHub.hub_connect_ip = '10.100.203.237'  # Внешний IP для подключения
c.JupyterHub.hub_port = 8081     # Hub internal API port
#c.JupyterHub.hub_bind_url = 'http://0.0.0.0:8081/hub/'
#c.JupyterHub.base_url = '/'
#c.JupyterHub.hub_prefix = '/hub/'

#Включить возможность иметь более 1 сервера у юзеров
c.JupyterHub.allow_named_servers = True

c.Spawner.enable_user_api = True #включить api
#настройки прокси
c.ConfigurableHTTPProxy.api_url = 'http://localhost:8001'
c.ConfigurableHTTPProxy.should_start = True
c.ConfigurableHTTPProxy.debug = True

#regex, по которым batchspawner парсит состояния задач
c.SlurmSpawner.state_pending_re = r'^PENDING|^CONFIGURING|^PD'
c.SlurmSpawner.state_running_re = r'^RUNNING|^COMPLETING|^R'
c.SlurmSpawner.state_exechost_re = r'\s+([\w\.-]+)$'

#настройка дамми авторизации
from dummyauthenticator import DummyAuthenticator

c.JupyterHub.authenticator_class = DummyAuthenticator
c.DummyAuthenticator.allowed_users = {"michman"}  # Разрешить пользователей таких
c.DummyAuthenticator.password = "" 

#Список админов
c.Authenticator.admin_users = {'michman'}

c.Spawner.debug = True #включить логи для спавнеров

c.SlurmSpawner.ip = '0.0.0.0' 

c.JupyterHub.api_tokens = {
'85919901e99e4e438acfc5cd7d41c851': 'michman' #
}


# ВАЖНО: Ручная настройка OAuth клиентов
c.JupyterHub.services = [
    {
        "name": "michman-jupyter-service",
        "api_token": "85919901e99e4e438acfc5cd7d41c851",
        "oauth_client_id": "service-michman-jupyter",
        "oauth_redirect_uri": "/user/michman/oauth_callback",
        "oauth_no_confirm": True,
    }
]


# Дополнительные OAuth настройки





c.JupyterHub.spawner_class = 'wrapspawner.ProfilesSpawner' #данный тип спавнера позволяет делать профилирование серверов

#SSH - тк JupyterHUB живет не на SLURM-кластере
# slurm-cluster - настройка конфига ssh на сервер SLURM-master
c.SlurmSpawner.batch_submit_cmd = 'ssh slurm-cluster sbatch --parsable' #команда на запуск
c.SlurmSpawner.batch_query_cmd = 'ssh slurm-cluster \"squeue -h -j {{job_id}} -o \"%T\";squeue -h -j {{job_id}} -o \"%N\"\"' #команда возвращает состояние задачи и имя узла, где она запускается
c.SlurmSpawner.batch_cancel_cmd = 'ssh slurm-cluster scancel {{job_id}}' #Завершить задачу

#Профили, которые доступны пользователям при запуске
c.ProfilesSpawner.profiles = [('🖥️ Small (2CPU, 4GB)', 'small.2cpu.4ram', 'batchspawner.SlurmSpawner', {
            'req_cores': '2',
            'req_partition': 'main',
            'req_memory': '4G',
            'req_runtime': '01:00:00',
            'batch_script': '''#!/bin/bash
#SBATCH --partition={{partition}}
#SBATCH --nodes=1
#SBATCH --mem=4G
#SBATCH --time={{runtime}}
#SBATCH --job-name=jupyter-{{username}}
#SBATCH --nodelist=michmanc3ab4d15-3d62-4d03-879d-011ddbd7f6f3
#SBATCH --output=/home/michman/jupyter-{{username}}-%j.log
#SBATCH --error=/home/michman/jupyter-error-{{username}}-%j.log
#SBATCH --gres=gpu:1
#SBATCH --export=ALL


NODE_HOSTNAME=$(hostname -f)
NODE_IP=10.100.192.63

# Настройка среды
export JUPYTERHUB_API_TOKEN='85919901e99e4e438acfc5cd7d41c851'
#export JUPYTERHUB_API_TOKEN='dummy-token-123'
export JUPYTERHUB_HOST='http://10.100.203.237:8888'
export JUPYTERHUB_API_URL='http://10.100.203.237:8081/hub/api'

export JUPYTERHUB_SERVICE_PREFIX='/user/{{username}}/'
#export JUPYTERHUB_BASE_URL='http://10.100.203.237:8888'

#export PATH=/home/michman/.local/bin:/usr/local/bin:/usr/bin:$PATH
#export PATH=/home/michman/.local/bin:$PATH
export XDG_RUNTIME_DIR=""

#export JUPYTERHUB_PUBLIC_URL="http://$NODE_IP:8888"
#export JUPYTERHUB_SERVICE_URL="http://10.100.203.237:8888"

export JUPYTERHUB_USER='{{username}}'
#export JUPYTERHUB_CLIENT_ID='jupyterhub-user-{{username}}'
export JUPYTERHUB_CLIENT_ID='service-michman-jupyter'

# Параметры сервера
#export JUPYTERHUB_OAUTH_CLIENT_ID='jupyterhub-user-{{username}}'
#export JUPYTERHUB_OAUTH_CALLBACK_URL='/user/{{username}}/oauth_callback'
#export JUPYTERHUB_OAUTH_HOST='http://10.100.203.237:8888'
#export JUPYTERHUB_OAUTH_CLIENT_SECRET='85919901e99e4e438acfc5cd7d41c851'

export DOCKER_IMAGE="docker.io/jupyter/datascience-notebook:latest"
export DOCKER_NAME="jupyter-{{username}}-${SLURM_JOB_ID}"

# Find available port
SERVERNAME={{servername}}
PORT=$(python -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()")

cat > /tmp/port_data.json << EOF
{{ '{ "port" : $PORT, "name" : "$SERVERNAME" }' | safe }}
EOF

# Report to hub
curl -X POST \
  -H "Authorization: token $JUPYTERHUB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/port_data.json \
  "$JUPYTERHUB_API_URL/batchspawner"




enroot start jupyter /bin/bash -c "
export JUPYTERHUB_API_TOKEN='85919901e99e4e438acfc5cd7d41c851' 
export JUPYTERHUB_HOST='http://10.100.203.237:8888' 
export JUPYTERHUB_API_URL='http://10.100.203.237:8081/hub/api' 
export JUPYTERHUB_SERVICE_PREFIX='/user/{{username}}/' 
export JUPYTERHUB_USER='{{username}}' 
export JUPYTERHUB_CLIENT_ID='service-michman-jupyter' 
export PORT=$PORT 
jupyter server \
    --ip=0.0.0.0 \
    --port=$PORT \
    --no-browser \
    --ServerApp.base_url=/user/{{username}}/{{servername}} \
    --ServerApp.default_url=/lab \
    --ServerApp.allow_origin="*" \
    --ServerApp.disable_check_xsrf=True \
    --IdentityProvider.token='' \
    --ServerApp.password='' \
    --HubAuth.api_token=$JUPYTERHUB_API_TOKEN \
    --ServerApp.token='' \
    --HubAuth.hub_host='http://10.100.203.237:8888'
"

# Логирование состояния контейнера




'''
        }), ('🖥️ Medium(4CPU, 8GB)', 'medium.4cpu.8ram', 'batchspawner.SlurmSpawner', {
            'req_cores': '4',
            'req_partition': 'main',
            'req_memory': '8G',
            'req_runtime': '01:00:00',
            'batch_script': '''#!/bin/bash
#SBATCH --partition={{partition}}
#SBATCH --nodes=1
#SBATCH --mem={{memory}}
#SBATCH --time={{runtime}}
#SBATCH --job-name=jupyter-{{username}}
#SBATCH --nodelist=michmanc3ab4d15-3d62-4d03-879d-011ddbd7f6f3
#SBATCH --output=/home/michman/jupyter-{{username}}-%j.log
#SBATCH --error=/home/michman/jupyter-error-{{username}}-%j.log
#SBATCH --export=ALL

NODE_HOSTNAME=$(hostname -f)
NODE_IP=10.100.192.63

# Настройка среды
export JUPYTERHUB_API_TOKEN='85919901e99e4e438acfc5cd7d41c851'
export JUPYTERHUB_HOST='http://10.100.203.237:8081'
export JUPYTERHUB_API_URL='http://10.100.203.237:8081/hub/api'

#export PATH=/home/michman/.local/bin:/usr/local/bin:/usr/bin:$PATH
#export PATH=/home/michman/.local/bin:$PATH
export XDG_RUNTIME_DIR=""

#export JUPYTERHUB_PUBLIC_URL="http://$NODE_IP:8888"
#export JUPYTERHUB_SERVICE_URL="http://$NODE_IP:8888"

export JUPYTERHUB_USER='michman'
#export JUPYTERHUB_CLIENT_ID='{{username}}'

# Параметры сервера
#export JUPYTERHUB_OAUTH_CLIENT_ID='{{username}}'
#export JUPYTERHUB_OAUTH_CALLBACK_URL='/user/{{username}}/oauth_callback'
#export JUPYTERHUB_OAUTH_HOST='http://10.100.203.237:8888'

# Find available port
SERVERNAME={{servername}}
PORT=$(python -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()")

cat > /tmp/port_data.json << EOF
{{ '{ "port" : $PORT, "name" : "$SERVERNAME" }' | safe }}
EOF

# Report to hub
curl -X POST \
  -H "Authorization: token $JUPYTERHUB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/port_data.json \
  "$JUPYTERHUB_API_URL/batchspawner"






# Запуск Jupyter
jupyter server \
    --ip=0.0.0.0 \
    --port=$PORT \
    --no-browser \
    --ServerApp.base_url=/user/{{username}}/{{servername}} \
    --ServerApp.default_url=/lab \
    --ServerApp.allow_origin="*" \
    --ServerApp.disable_check_xsrf=True \
    --IdentityProvider.token='' \
    --ServerApp.password=''
'''
        }), ('🖥️ GPU_Medium(4CPU, 8GB)', 'medium.4cpu.8ram.tesla_a100', 'batchspawner.SlurmSpawner', {
            'req_cores': '4',
            'req_partition': 'main',
            'req_memory': '8G',
            'req_runtime': '01:00:00',
            'batch_script': '''#!/bin/bash
#SBATCH --partition={{partition}}
#SBATCH --nodes=1
#SBATCH --mem={{memory}}
#SBATCH --time={{runtime}}
#SBATCH --job-name=jupyter-{{username}}
#SBATCH --nodelist=michmanc3ab4d15-3d62-4d03-879d-011ddbd7f6f3
#SBATCH --output=/home/michman/jupyter-{{username}}-%j.log
#SBATCH --error=/home/michman/jupyter-error-{{username}}-%j.log
#SBATCH --gres=gpu:1
#SBATCH --export=ALL

NODE_HOSTNAME=$(hostname -f)
NODE_IP=10.100.192.63

# Настройка среды
export JUPYTERHUB_API_TOKEN='85919901e99e4e438acfc5cd7d41c851'
export JUPYTERHUB_HOST='http://10.100.203.237:8081'
export JUPYTERHUB_API_URL='http://10.100.203.237:8081/hub/api'

#export PATH=/home/michman/.local/bin:/usr/local/bin:/usr/bin:$PATH
#export PATH=/home/michman/.local/bin:$PATH
export XDG_RUNTIME_DIR=""

#export JUPYTERHUB_PUBLIC_URL="http://$NODE_IP:8888"
#export JUPYTERHUB_SERVICE_URL="http://$NODE_IP:8888"

export JUPYTERHUB_USER='michman'
#export JUPYTERHUB_CLIENT_ID='{{username}}'

# Параметры сервера
#export JUPYTERHUB_OAUTH_CLIENT_ID='{{username}}'
#export JUPYTERHUB_OAUTH_CALLBACK_URL='/user/{{username}}/oauth_callback'
#export JUPYTERHUB_OAUTH_HOST='http://10.100.203.237:8888'

# Find available port
SERVERNAME={{servername}}
PORT=$(python -c "import socket; s=socket.socket(); s.bind(('', 0)); print(s.getsockname()[1]); s.close()")

cat > /tmp/port_data.json << EOF
{{ '{ "port" : $PORT, "name" : "$SERVERNAME" }' | safe }}
EOF

# Report to hub
curl -X POST \
  -H "Authorization: token $JUPYTERHUB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/port_data.json \
  "$JUPYTERHUB_API_URL/batchspawner"






# Запуск Jupyter
jupyter server \
    --ip=0.0.0.0 \
    --port=$PORT \
    --no-browser \
    --ServerApp.base_url=/user/{{username}}/{{servername}} \
    --ServerApp.default_url=/lab \
    --ServerApp.allow_origin="*" \
    --ServerApp.disable_check_xsrf=True \
    --IdentityProvider.token='' \
    --ServerApp.password=''
'''
        })]












c.SlurmSpawner.start_timeout = 300
c.SlurmSpawner.http_timeout = 60
c.JupyterHub.user = 'michman' #от имени кого запускать все
c.JupyterHub.db_url = 'sqlite:////home/jupyter/.jupyter/jupyterhub.sqlite' #путь до бд


