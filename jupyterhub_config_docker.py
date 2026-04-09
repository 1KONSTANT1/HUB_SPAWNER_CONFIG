# minimal_config.py
from dummyauthenticator import DummyAuthenticator  # ← правильный импорт
from oauthenticator import GitHubOAuthenticator
import asyncio
import asyncssh
import random
import socket
from traitlets import Unicode, Integer, List, Dict, default
from jupyterhub.spawner import Spawner
import logging
c = get_config()





MICHMAN_API_TOKEN = '85919901e99e4e438acfc5cd7d41c851'
JUPYTER_API_TOKEN = '85919901e99e4e438acfc5cd7d41c852'


class SimpleSSHSpawner(Spawner):
    """SSHSpawner для запуска Jupyter в Docker контейнере"""
    
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
    
    docker_image = Unicode(
        "jup_client",
        help="Docker образ для запуска",
        config=True
    )
    
    docker_network = Unicode(
        "bridge",
        help="Docker сеть",
        config=True
    )
    
    docker_mounts = List(
        trait=Unicode(),
        default_value=['source=nfs-volume,target=/work'],
        help="Список монтирований для Docker контейнера",
        config=True
    )
    
    ssh_config = Dict(
        default_value={'connect_timeout': 30},
        help="Конфигурация SSH подключения",
        config=True
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.container_id = None  # ID Docker контейнера вместо pid
        self.remote_host = None
        self.remote_ip = None
        self.log = logging.getLogger(__name__)
    
    def resolve_host(self, hostname):
        """Разрешение хоста в IP адрес"""
        try:
            socket.inet_aton(hostname)
            return hostname
        except socket.error:
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
            for h in self.remote_hosts:
                ip = self.resolve_host(h)
                if ip:
                    self.log.info(f"Fallback to host {h} -> {ip}")
                    return ip
            raise ValueError(f"Cannot resolve any host from {self.remote_hosts}")
    
    async def start(self):
        """Запуск Jupyter в Docker контейнере на удаленном хосте"""
        try:
            # Выбираем и резолвим хост
            self.remote_ip = self.choose_remote_host()
            if not self.remote_ip:
                raise ConnectionError(f"Cannot resolve host")
            
            username = self.user.name
            ssh_keyfile = self.ssh_keyfile
            
            self.log.info(f"Connecting to {self.remote_ip}:{self.ssh_port} as {username}")
            
            # Подключаемся по SSH
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username="michman",
                client_keys=[ssh_keyfile],
                known_hosts=None,
                connect_timeout=30,
                login_timeout=30
            ) as conn:
                
                self.log.info("SSH connection established")
                
                
                # Получаем свободный порт на хосте
                port_cmd = '''python3 -c "
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
                
                host_port = int(result.stdout.strip())
                
                #host_port = 6666
                container_port = 8888
                
                self.log.info(f"Using host port: {host_port} -> container port: {container_port}")



                token = ""

                if username == "michman":
                    token = MICHMAN_API_TOKEN
                else:
                    token = JUPYTER_API_TOKEN
                
                # Формируем команду Jupyter для выполнения внутри контейнера
                jupyter_cmd = (
                    f'jupyterhub-singleuser '
                    f'--ip=0.0.0.0 '
                    f'--allow-root '
                    f'--port={container_port} '
                    f'--gateway-url=http://10.100.203.237:5555 '
                    f'--MappingKernelManager.buffer_offline_messages=False '
                    f'--no-browser '
                    f'--ServerApp.default_url=/lab '
                    f'--ServerApp.base_url=/user/{username}/ '
                    f'--ServerApp.allow_origin=* '
                    f'--ServerApp.disable_check_xsrf=True '
                    f'--IdentityProvider.token="" '
                    f'--ServerApp.password="" '
                    f'--ServerApp.token="" '
                    f'--LabApp.extension_manager="pypi"'
                )

                envikk = self.get_env()

                docker_args = []
                for key, value in envikk.items():
                    escaped_value = str(value).replace('"', '\\"')
                    docker_args.append(f'-e {key}="{escaped_value}"')
                
                envikk = ' '.join(docker_args)
                envikk += f" -e KERNEL_USERNAME={username}"
                print(f"\n\n\n ENVAARSSS  {envikk}  \n\n\n ")
                print(f"\n\n\n NAMEEEEE  {username}  \n\n\n ")
                
                # Формируем переменные окружения для контейнера
                env_vars = [
                f'-e JUPYTERHUB_USER={username}',
                f'-e JUPYTERHUB_API_TOKEN={token}',
                f'-e JUPYTERHUB_API_URL=http://10.100.203.237:8081/hub/api',
                f'-e JUPYTERHUB_CLIENT_ID=service-{username}-jupyter',
                f'-e JUPYTERHUB_HOST=http://10.100.203.237:8888',
                f'-e JUPYTERHUB_SERVICE_URL=http://10.100.203.237:8888',
                f'-e JUPYTERHUB_SERVICE_PREFIX=/user/{username}/',
                f'-e XDG_RUNTIME_DIR=""',
                f'-e KERNEL_USERNAME={username}'
                ]
                env_str = ' '.join(env_vars)
                
                # Формируем mounts
                mounts = []
                for mount in self.docker_mounts:
                    mounts.append(f'--mount {mount}')
                mounts_str = ' '.join(mounts)
                
                # Формируем полную Docker команду --mount source=nfs_data_{username},target=/work 
                docker_cmd = (
                    f'docker run -d --rm '
                    f'--restart=no '
                    f'--network={self.docker_network} '
                    f'-p {host_port}:{container_port} '
                    f'-v ~/nfs_data/{username}:/work '
                    f'{envikk} '
                    f'--name client-{username}-{random.randint(1000, 9999)} '
                    f'{self.docker_image} '
                    f'/bin/bash -c "source /etc/bash.bashrc && timelimit -t 43200 {jupyter_cmd} 2>&1 | tee /tmp/jupyter_{username}.log"'
                )
                
                self.log.info(f"Starting Docker container on {self.remote_ip}")
                self.log.debug(f"Docker command: {docker_cmd}")


                #sudo docker volume create --driver local --opt type=nfs --opt o='addr=10.100.203.132,rw,nfsvers=4,soft' --opt device=:/data/{username} nfs_data_{username} > /dev/null;
                
                # Запускаем контейнер
                result = await conn.run(f"mkdir -p ~/nfs_data/{username};sudo mount -t nfs 10.100.203.132:/data/{username} ~/nfs_data/{username}; {docker_cmd}")
                
                if result.exit_status != 0:
                    error_msg = result.stderr or result.stdout
                    raise ConnectionError(f"Failed to start Docker container: {error_msg}")
                
                # Получаем ID контейнера
                container_id = result.stdout.strip()
                
                # Проверяем, что контейнер действительно запустился
                check_cmd = f'docker ps -q --filter "id={container_id}"'
                check_result = await conn.run(check_cmd)
                
                if not check_result.stdout.strip():
                    # Проверяем логи если контейнер не запустился
                    logs_cmd = f'docker logs {container_id}'
                    logs_result = await conn.run(logs_cmd)
                    self.log.error(f"Container failed to start. Logs: {logs_result.stdout}")
                    raise ConnectionError("Container exited immediately")
                
                self.container_id = container_id
                self.log.info(f"Jupyter container started with ID: {container_id} on port {host_port}")
                
                return self.remote_ip, str(host_port)
                
        except asyncssh.Error as e:
            self.log.error(f"SSH connection error: {e}")
            raise ConnectionError(f"SSH failed: {e}")
        except Exception as e:
            self.log.error(f"Unexpected error: {e}")
            raise
    
    async def poll(self):
        """Проверка работает ли контейнер"""
        if not hasattr(self, 'container_id') or not self.container_id:
            return 0
        
        if not self.remote_ip:
            return 0
        
        try:
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username="michman",
                client_keys=[self.ssh_keyfile],
                known_hosts=None,
                connect_timeout=30,
                login_timeout=30
            ) as conn:
                # Проверяем статус контейнера
                result = await conn.run(f'docker ps -q --filter "id={self.container_id}"')
                is_running = bool(result.stdout.strip())
                
                if is_running:
                    return None  # Контейнер работает
                else:
                    # Проверяем существует ли контейнер (остановлен)
                    result = await conn.run(f'docker ps -a -q --filter "id={self.container_id}"')
                    if result.stdout.strip():
                        self.log.info(f"Container {self.container_id} exists but not running")
                    return 0  # Контейнер не работает
                    
        except Exception as e:
            self.log.error(f"Error checking container status: {e}")
            return 0  # Считаем процесс мертвым при ошибке
    

    async def my_pre_spawn_hook(self):
        try:
            async with asyncssh.connect(
                "10.100.203.132",
                port=self.ssh_port,
                username="michman",
                client_keys=["/home/jupyter/.ssh/jupyterhub_slurm"],
                known_hosts=None,
                connect_timeout=30,
                login_timeout=30
            ) as conn:
                user = self.user.name
                data_dir = f"/data/{user}"
                #sudo chown 1000:1000 "{data_dir}" && \\
                # Выполняем все операции одной командой через && для атомарности   rw,sync,no_subtree_check,no_root_squash
                setup_script = f'''
                    sudo mkdir "{data_dir}" && \\
                    sudo chown 65534:65534 "{data_dir}" && \\
                    sudo chmod 777 "{data_dir}" && \\
                    echo "{data_dir} *(rw,sync,no_subtree_check,all_squash,anonuid=65534,anongid=65534,sec=sys)" >> /etc/exports && \\
                    sudo exportfs -ra
                '''
                
                result = await conn.run(setup_script)
                
                if result.exit_status != 0:
                    error_msg = result.stderr or result.stdout
                    self.log.info(f"Failed to set up directory: {error_msg}")
                
                self.log.info(f"Successfully set up {data_dir} for user {user}")
                        
        except Exception as e:
            self.log.error(f"Error in pre-spawn hook: {e}")
            raise
    
    async def stop(self, now=False):
        """Остановка и удаление Docker контейнера"""
        print(f"\n\n\n  STTTTOOTOTOOTOTOTOTOp \n\n\n")
        username = self.user.name
        if not hasattr(self, 'container_id') or not self.container_id or not self.remote_ip:
            
            print(f"\n\n\n  WATAFAAAAAAAAK      EKOKOEEKOEOKEOKOEKKEOKEOKEOKEOKEOOEKOKEEKOOEK")
            return
        
        try:
            async with asyncssh.connect(
                self.remote_ip,
                port=self.ssh_port,
                username="michman",
                client_keys=[self.ssh_keyfile],
                known_hosts=None,
                connect_timeout=30,
                login_timeout=30
            ) as conn:
                signal = 9 if now else 15
                
                self.log.info(f"Stopping container {self.container_id} with signal {signal}")
                
                
                if now:
                    # Принудительная остановка
                    await conn.run(f'docker kill {self.container_id} 2>/dev/null || true')
                else:
                    # Мягкая остановка
                    print(f"\n\n\n  !%!%!%%!%!%!%%!!%%!%!%151515155151515151515151\n\n\n")
                    await conn.run(f'docker exec {self.container_id} /bin/bash -c \"jupyter lab stop;kill -15 -1\" 2>/dev/null || true; sudo umount ~/nfs_data/{username};')
                    print(f"\n\n\n  EKOKOEEKOEOKEOKOEKKEOKEOKEOKEOKEOOEKOKEEKOOEK")
                    #await conn.run(f'docker kill {self.container_id} 2>/dev/null || true')
                
                # Даем время на graceful shutdown
                await asyncio.sleep(2)
                
                # Удаляем контейнер
                await conn.run(f'docker rm {self.container_id}')
                
        except Exception as e:
            self.log.error(f"Error stopping container: {e}")
        finally:
            self.container_id = None
            self.remote_ip = None

c.JupyterHub.spawner_class = SimpleSSHSpawner  # ← правильное использование

c.JupyterHub.confirm_no_ssl = True
#c.JupyterHub.ssl_key = '/etc/jupyterhub/ssl/jupyterhub.key'
#c.JupyterHub.ssl_cert = '/etc/jupyterhub/ssl/jupyterhub.crt'


c.JupyterHub.port = 8888 #Порт где работает JupyterHUB
c.JupyterHub.hub_ip = '0.0.0.0'  # Hub слушает на всех интерфейсах
c.JupyterHub.hub_connect_ip = '10.100.203.237'  # Внешний IP для подключения
c.JupyterHub.hub_port = 8081     # Hub internal API port



c.ConfigurableHTTPProxy.api_url = 'http://localhost:8001'
c.ConfigurableHTTPProxy.should_start = True
c.ConfigurableHTTPProxy.debug = True




c.JupyterHub.authenticator_class = GitHubOAuthenticator
#c.JupyterHub.authenticator_class = DummyAuthenticator
#c.DummyAuthenticator.allowed_users = {"michman", "jupyter"}  # Разрешить пользователей таких
#c.DummyAuthenticator.password = "" 

c.OAuthenticator.oauth_callback_url = "http://10.100.203.237:8888/hub/oauth_callback"
c.OAuthenticator.client_id = "Ov23lipaXiFVgYa65SXU"
c.OAuthenticator.client_secret = "73d9dc8131edc5675e8d6b29cae7477062d9c61b"

c.Authenticator.allow_all = True


#c.JupyterHub.api_tokens = {
#MICHMAN_API_TOKEN: 'michman',
#JUPYTER_API_TOKEN: 'jupyter' #
#}

#Список админов
c.Authenticator.admin_users = {"michman", "jupyter", "1konstant1"}

c.JupyterHub.load_roles = [
    {
        "name": "admin",
        "users": ["1konstant1"],  # email или username из OAuth
    }
]

# ВАЖНО: Ручная настройка OAuth клиентов
#c.JupyterHub.services = [
   # {
     #   "name": "michman-jupyter-service",
      #  "api_token": MICHMAN_API_TOKEN,
      #  "oauth_client_id": "service-michman-jupyter",
      #  "oauth_redirect_uri": "/user/michman/oauth_callback",
      #  "oauth_no_confirm": True,
    #},
    #{
     #   "name": "jupyter-jupyter-service",
     # #  "api_token": JUPYTER_API_TOKEN,
      #  "oauth_client_id": "service-jupyter-jupyter",
    #    "oauth_redirect_uri": "/user/jupyter/oauth_callback",
     #   "oauth_no_confirm": True,
   # }
#]

c.JupyterHub.internal_ssl = False

c.Spawner.pre_spawn_hook = c.JupyterHub.spawner_class.my_pre_spawn_hook

# Настройки SSH подключения
c.SimpleSSHSpawner.remote_hosts = ['slurm-gateway']
#c.SSHSpawner.username = '{username}'  # Подставляется имя пользователя JupyterHub

# Использование SSH ключей (рекомендуется)
c.SimpleSSHSpawner.ssh_keyfile = '/home/jupyter/.ssh/jupyterhub_slurm'
