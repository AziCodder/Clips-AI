# Подключение Cursor к серверу (Hostkey) через Remote SSH

Чтобы редактировать код прямо на сервере и сразу видеть изменения, подключи Cursor к серверу по SSH.

## 1. Установка расширения в Cursor

1. Открой Cursor → **Extensions** (Ctrl+Shift+X).
2. Найди и установи **Remote - SSH** от **Cursor** (`anysphere.remote-ssh`).
3. **Не используй** расширение от Microsoft (`ms-vscode-remote.remote-ssh`) — у Cursor своя версия с лучшей поддержкой.

## 2. SSH-ключ (если ещё нет)

На Windows в PowerShell:

```powershell
# Проверь, есть ли ключ
dir $env:USERPROFILE\.ssh

# Если нет — создай (email замени на свой)
ssh-keygen -t ed25519 -C "your_email@example.com" -f "$env:USERPROFILE\.ssh\id_ed25519"
```

Публичный ключ должен быть на сервере в `~/.ssh/authorized_keys` у пользователя, под которым подключаешься (например `deploy` или `root`).

## 3. Конфиг SSH на твоём ПК

Добавь хост в конфиг SSH. На Windows файл:  
`C:\Users\<ТвойПользователь>\.ssh\config`

Создай или отредактируй `config` (без расширения), подставь **IP или hostname** своего сервера Hostkey и пользователя:

```sshconfig
# Сервер CLIP AI на Hostkey (CPU / деплой)
Host hostkey-clips
    HostName YOUR_SERVER_IP_OR_HOSTNAME
    User deploy
    IdentityFile ~/.ssh/id_ed25519
```

Если подключаешься под `root`:

```sshconfig
Host hostkey-clips
    HostName YOUR_SERVER_IP_OR_HOSTNAME
    User root
    IdentityFile ~/.ssh/id_ed25519
```

- `YOUR_SERVER_IP_OR_HOSTNAME` — замени на реальный IP или домен сервера (например из панели Hostkey).
- `deploy` — пользователь из [DEPLOY_FULL.md](DEPLOY_FULL.md); если используешь `root`, укажи `User root`.
- Путь `/home/deploy/clips` — стандартный из гайда; если у тебя другой каталог проекта, поменяй в конфиге или при подключении выбери нужную папку.

## 4. Подключение из Cursor

1. **Ctrl+Shift+P** → команда **Remote-SSH: Connect to Host...**.
2. Выбери хост **hostkey-clips** (или как назвал в `config`).
3. Откроется новое окно Cursor, подключённое к серверу.
4. **File → Open Folder** → укажи папку проекта на сервере, например `/home/deploy/clips`.

Дальше все правки в файлах будут сразу на сервере.

## 5. Если не подключается

### Ошибка «Connection closed by … port 22» (код 255)

Сервер обрывает соединение. Чаще всего мешают настройки **на сервере**.

**1. Разрешить TCP-проброс (Cursor использует туннель `-D`):**

На сервере отредактируй `/etc/ssh/sshd_config`:

```bash
# Должно быть (раскомментируй или добавь):
AllowTcpForwarding yes
```

Перезапусти SSH: `systemctl restart sshd` (или `ssh` на некоторых системах).

**2. Проверить .profile / .bashrc у root:**

Если при неинтерактивном входе скрипт делает `exit`, соединение будет рваться. Подключись обычным SSH и посмотри:

```bash
ssh myserver
cat /root/.bashrc
cat /root/.profile
```

В `.bashrc` в начале часто есть блок «если не интерактивный — выйти». Убедись, что там нет лишнего `exit` для неинтерактивного режима. При необходимости в самом начале `.bashrc` можно добавить:

```bash
# Для Remote SSH (Cursor/VS Code) — не выходить при неинтерактивном запуске
[[ -n "$VSCODE_SSH" ]] && return 0
```

**3. В конфиге на своём ПК для этого хоста:**

- Для Cursor поставь `RequestTTY yes` (уже стоит в примере выше).
- Убедись, что нет `RequestTTY no` для хоста, к которому подключаешься из Cursor.

**4. Обычный SSH должен работать:**

В PowerShell выполни: `ssh myserver` — зайти и выйти (`exit`). Если так подключаешься без ошибок, значит проблема именно в туннеле или в установке Cursor server; тогда в первую очередь проверь пункт 1 (AllowTcpForwarding).

### Прочие советы

- **Таймаут**: в настройках расширения Remote-SSH увеличь `remote.SSH.connectTimeout` (например до 60).
- **Прокси**: если есть корпоративный прокси, задай в настройках Cursor `http.proxy` / `https.proxy` или переменные `HTTP_PROXY` / `HTTPS_PROXY`.
- **Мультиплексор SSH**: при нестабильном соединении в `~/.ssh/config` закомментируй строки `ControlPath`, `ControlMaster`, `ControlPersist` для этого хоста.

## 6. После подключения

- Терминал в Cursor выполняется на сервере — можно запускать `docker compose`, миграции, логи.
- Расширения (Python, ESLint и т.д.) можно ставить на remote — Cursor предложит установить их на сервер при первом открытии файлов.

Если сервер именно на Hostkey, IP или hostname смотри в панели [panel.hostkey.com](https://panel.hostkey.com) у своего VPS.

---

## Другие способы (без Remote SSH)

Если Remote SSH не подходит (ошибки подключения, не хочешь трогать `sshd_config`), можно работать так:

### 1. SFTP: правки локально → авто-загрузка на сервер

Ты работаешь в **локальной** папке проекта в Cursor; расширение по SFTP при сохранении файла заливает его на сервер. Никаких туннелей и Cursor Server на сервере не нужно.

**Шаги:**

1. Установи расширение **SFTP** (автор: Natizyskunk) — в Cursor: **Extensions** (Ctrl+Shift+X) → поиск «SFTP» → **SFTP** от Natizyskunk → Install.
2. Открой **корневую папку проекта** в Cursor (File → Open Folder → папка «Автоматизация 2»).
3. В проекте уже есть готовый конфиг **`.vscode/sftp.json`** (он не коммитится в git). Если его нет — **Ctrl+Shift+P** → **SFTP: Config** — создастся шаблон, скопируй в него настройки ниже.
4. Проверь в `.vscode/sftp.json`:
   - **host** — IP сервера (31.207.55.254 или твой).
   - **username** — `root` или `deploy`.
   - **remotePath** — путь к проекту на сервере: `/root/clips` для root, `/home/deploy/clips` для пользователя deploy.
   - **privateKeyPath** — путь к ключу на твоём ПК (например `C:/Users/ТвойЛогин/.ssh/id_ed25519`). Если входишь по паролю — удали строку `privateKeyPath` и добавь `"password": "твой_пароль"` (не коммить!).
5. При сохранении файла (Ctrl+S) он автоматически загружается на сервер. Вручную: правый клик по папке/файлу → **SFTP: Upload**.

**Плюсы:** не зависит от AllowTcpForwarding, всё как обычный SSH. **Минус:** терминал в Cursor локальный; команды на сервере запускаешь отдельно (например через `ssh myserver`).

---

### 2. SSHFS: смонтировать папку сервера как диск

Папка с сервера показывается в Windows как сетевой диск; в Cursor открываешь эту папку и редактируешь файлы «на диске» — на самом деле они на сервере.

**Шаги:**

1. Установи **WinFsp** и **SSHFS-Win** (или **SSHFS-Win** из Microsoft Store / [GitHub](https://github.com/winfsp/sshfs-win)).
2. В проводнике: **Подключить сетевой диск** или используй утилиту из SSHFS-Win — укажи хост `31.207.55.254`, пользователь `root`, путь `/root/clips` (или `/home/deploy/clips`).
3. В Cursor: **File → Open Folder** → выбери смонтированный диск (например `S:\` или `\\sshfs\root@31.207.55.254\root\clips`).

**Плюсы:** ощущение «всё на сервере», без расширений Cursor. **Минусы:** нужна установка драйвера; при обрыве сети диск может «зависнуть».

---

### 3. Git: правишь локально → пушишь → на сервере pull

Код живёт в репозитории; на сервере просто делаешь `git pull` после твоих правок (или настроен деплой через CI/GitHub Actions).

- Локально в Cursor: правки → `git commit` → `git push`.
- На сервере: `ssh myserver`, `cd /home/deploy/clips`, `git pull`, при необходимости перезапуск контейнеров.

**Плюсы:** привычный workflow, история, откат. **Минус:** изменения не «сразу на сервере», нужен явный деплой (push + pull или скрипт).
