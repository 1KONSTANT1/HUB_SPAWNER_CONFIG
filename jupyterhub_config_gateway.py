# minimal_config.py
from dummyauthenticator import DummyAuthenticator  # ← правильный импорт
import asyncio
import asyncssh
import random
import socket
from traitlets import Unicode, Integer, List, Dict, default
from jupyterhub.spawner import Spawner
import logging


class SimpleSSHSpawner(Spawner):
    """Исправленный SSHSpawner с обработкой ошибок"""
    
    remote_hosts = List(
        trait=Unicode(),
        default_value=['localhost'],
        help="Список удаленных хостов (IP адреса или домены)",
        config=True
    )
    
    ssh_port = Integer(
        22,
        help="SSH порт",
        config=True
    )
    
    ssh_keyfile = Unicode(
        "~/.ssh/id_rsa",
        help="Путь к SSH приватному ключу",
        config=True
    )
    
    remote_python = Unicode(
        "python3",
        help="Python на удаленном хосте",
        config=True
    )
    
    ssh_config = Dict(
        default_value={'connect_timeout': 30},
        help="Конфигурация SSH подключения",
        config=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pid = None  # Инициализируем pid
        self.remote_host = None
        self.remote_ip = None
        self.log = logging.getLogger(__name__)
    
    def resolve_host(self, hostname):
        """Разрешение хоста в IP адрес"""
        try:
            # Пробуем сначала как IP адрес
            socket.inet_aton(hostname)
            return hostname  # Уже IP
        except socket.error:
            # Разрешаем доменное имя
            try:
                return socket.gethostbyname(hostname)
            except socket.gaierror as e:
                self.log.error(f"Cannot resolve hostname {hostname}: {e}")
                return None
    
    def choose_remote_host(self):
        """Выбор удаленного хоста с резолвингом"""
        host = random.choice(self.remote_hosts)
        ip = self.resolve_host(host)
        if ip:
            self.log.info(f"Selected host {host} -> {ip}")
            return ip
        else:
            # Если не удалось разрешить, пробуем следующий
            for h in self.remote_hosts:
                ip = self.resolve_host(h)
                if ip:
                    self.log.info(f"Fallback to host {h} -> {ip}")
                    return ip
            raise ValueError(f"Cannot resolve any host from {self.remote_hosts}")
    
    async def start(self):
        """Запуск Jupyter на удаленном хосте"""
        try:
            # Выбираем и резолвим хост
            self.remote_ip = self.choose_remote_host()
            if not self.remote_ip:
                raise ConnectionError(f"Cannot resolve host")
            
            username = self.user.name
            ssh_keyfile = self.ssh_keyfile
            
            self.log.info(f"Connecting to {self.remote_ip}:{self.ssh_port} as {username}")
            
            # Подключаемся с таймаутами и обработкой ошибок
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username=username,
                client_keys=[ssh_keyfile],
                known_hosts=None,
                connect_timeout=30,
                login_timeout=30
            ) as conn:
                
                self.log.info("SSH connection established")
                
                # Получаем свободный порт
                port_cmd = f'''{self.remote_python} -c "
import socket
s = socket.socket()
s.bind(('', 0))
port = s.getsockname()[1]
s.close()
print(port)
"'''
                
                result = await conn.run(port_cmd)
                if result.exit_status != 0:
                    raise ConnectionError(f"Failed to get port: {result.stderr}")
                
                port = int(result.stdout.strip())
                self.log.info(f"Got free port: {port}")
                
                # Запускаем Jupyter
                cmd_parts = [
                    'jupyter-labhub',
                    f'--ip=0.0.0.0',
                    f'--port={port}',
                    '--no-browser',
                    # Важно: токен без кавычек внутри f-строки
                    f'--NotebookApp.token="85919901e99e4e438acfc5cd7d41c851"',  # JupyterHub сам генерирует токен
                    # Правильный base_url
                    f'--NotebookApp.base_url={self.server.base_url}',
                    # Остальные настройки безопасности
                    '--NotebookApp.allow_origin=*',
                    '--NotebookApp.disable_check_xsrf=True',
                    # Настройки ServerApp (JupyterLab 3.0+)
                    '--ServerApp.allow_origin=*',
                    '--ServerApp.disable_check_xsrf=True',
                    # Отключение пароля и токена для интеграции с JupyterHub
                    "--ServerApp.token=''",
                    "--ServerApp.password=''",
                    # Параметры для интеграции с JupyterHub
                    f'--HubOAuth.hub_prefix={self.hub.base_url}',
                    f'--HubOAuth.hub_host="http://10.100.203.237:8888"',
                    f'--HubOAuth.api_token="85919901e99e4e438acfc5cd7d41c851"',
                    # Перенаправление логов и получение PID
                    '> /tmp/jupyter_$USER.log 2>&1 & echo $!'
                ]
                
                cmd_str = ' '.join(cmd_parts)
                self.log.info(f"Running command: {cmd_str}")
                
                result = await conn.run(cmd_str)
                if result.exit_status != 0:
                    raise ConnectionError(f"Failed to start Jupyter: {result.stderr}")
                
                pid = int(result.stdout.strip())
                self.pid = pid
                self.log.info(f"Jupyter started with PID: {pid}")






                cmd = (
                    f'setsid nohup '
                    f'env JUPYTERHUB_API_TOKEN=85919901e99e4e438acfc5cd7d41c851 '
                    f'JUPYTERHUB_API_URL=http://10.100.203.237:8081/hub/api '
                    f'JUPYTERHUB_USER={username} '
                    f'JUPYTERHUB_SERVICE_PREFIX=/user/{username}/ '
                    f'jupyter-labhub --ip=0.0.0.0 --port={port} '
                    f'--no-browser '
                    f'--ServerApp.default_url=/lab '
                    f'--ServerApp.base_url=/user/{username}/ '
                    f'--ServerApp.allow_origin=* '
                    f'--ServerApp.disable_check_xsrf=True '
                    f'--HubOAuth.hub_prefix=/ '
                    f'--HubOAuth.hub_host=http://10.100.203.237:8888 '
                    f'--HubOAuth.api_token=85919901e99e4e438acfc5cd7d41c851 '
                    f'>/tmp/jupyter_{username}.log 2>&1 & echo $!'
                )
                
                return (self.remote_ip, port)
                
        except asyncssh.Error as e:
            self.log.error(f"SSH connection error: {e}")
            raise ConnectionError(f"SSH failed: {e}")
        except Exception as e:
            self.log.error(f"Unexpected error: {e}")
            raise
    
    async def poll(self):
        """Проверка работает ли процесс"""
        if not hasattr(self, 'pid') or self.pid is None:
            return 0  # Не запущен
        
        if not self.remote_ip:
            return 0
        
        try:
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username=self.user.name,
                client_keys=[self.ssh_keyfile],
                connect_timeout=10
            ) as conn:
                # Проверяем жив ли процесс
                result = await conn.run(f'ps -p {self.pid} > /dev/null 2>&1; echo $?')
                is_alive = int(result.stdout.strip()) == 0
                return None if is_alive else 0
        except:
            # Если не можем подключиться, считаем процесс мертвым
            return 0
        

        cmd = (
                    f'setsid nohup '
                    f'env JUPYTERHUB_API_TOKEN=85919901e99e4e438acfc5cd7d41c851 '
                    f'JUPYTERHUB_API_URL=http://10.100.203.237:8081/hub/api '
                    f'JUPYTERHUB_CLIENT_ID=service-michman-jupyter '
                    f'JUPYTERHUB_HOST=http://10.100.203.237:8888 '
                    f'JUPYTERHUB_USER={username} '
                    f'JUPYTERHUB_SERVICE_PREFIX=/user/{username}/ '
                    f'JUPYTERHUB_API_URL=http://10.100.203.237:8081/hub/api ' 
                    f'jupyter-labhub --ip=0.0.0.0 --port={port} '
                    f'--no-browser '
                    f'--ServerApp.default_url=/lab '
                    f'--ServerApp.base_url=/user/{username}/ '
                    f'--ServerApp.allow_origin=* '
                    f'--ServerApp.disable_check_xsrf=True '
                    f'--HubOAuth.hub_prefix=/ '
                    f'--HubOAuth.hub_host=http://10.100.203.237:8888 '
                    f'--HubOAuth.api_token=$JUPYTERHUB_API_TOKEN '
                    f'>/tmp/jupyter_{username}.log 2>&1 & echo $!'
                )
    
    async def stop(self, now=False):
        """Остановка процесса"""
        if not hasattr(self, 'pid') or not self.pid or not self.remote_ip:
            return
        
        try:
            signal = 9 if now else 15
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username=self.user.name,
                client_keys=[self.ssh_keyfile],
                connect_timeout=10
            ) as conn:
                await conn.run(f'kill -{signal} {self.pid} 2>/dev/null || true')
        except:
            pass
        finally:
            self.pid = None
            self.remote_ip = None

c.JupyterHub.spawner_class = SimpleSSHSpawner  # ← правильное использование


c.JupyterHub.authenticator_class = DummyAuthenticator
c.DummyAuthenticator.allowed_users = {"michman"}  # Разрешить пользователей таких
c.DummyAuthenticator.password = "" 

#Список админов
c.Authenticator.admin_users = {'michman'}

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

c.JupyterHub.internal_ssl = False

# Или если в вашем SSHSpawner есть настройка user_ssl
try:
    c.SSHSpawner.user_ssl = False
except:
    pass
# Настройки SSH подключения
c.SimpleSSHSpawner.remote_hosts = ['slurm-gateway']
#c.SSHSpawner.username = '{username}'  # Подставляется имя пользователя JupyterHub

# Использование SSH ключей (рекомендуется)
c.SimpleSSHSpawner.ssh_keyfile = '/home/jupyter/.ssh/jupyterhub_slurm'

# Команда запуска на удаленном сервере
c.SimpleSSHSpawner.cmd = ['jupyter-lab', '--ip', '0.0.0.0']
c.SimpleSSHSpawner.args = [
    '--no-browser',
    '--NotebookApp.token={"85919901e99e4e438acfc5cd7d41c851"}'
]

