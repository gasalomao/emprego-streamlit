import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, date
from streamlit_option_menu import option_menu
import google.generativeai as genai

# Configurar a API Gemini
api_key = "AIzaSyDm074LJFjlk-xVK42iCgXFPPwqF7BQ7E0"  # Substitua por sua chave de API real
if not api_key:
    st.error("A chave da API Gemini não está definida.")
    st.stop()

genai.configure(api_key=api_key)

# Configuração da página
st.set_page_config(
    page_title="Sistema de Gerenciamento de Tarefas",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS personalizado
st.markdown("""
<style>
    body {
        background-color: #f5f5f5;
    }
    .main-header {
        font-size: 32px;
        color: #2C3E50;
        font-weight: bold;
    }
    .sub-header {
        font-size: 24px;
        color: #34495E;
        font-weight: bold;
    }
    .task-container {
        background-color: #fff;
        padding: 15px;
        margin-bottom: 10px;
        border-radius: 5px;
    }
    .highlight {
        background-color: #FFFFCC;
    }
    .task-buttons {
        text-align: right;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Função para hash de senhas
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Classe para Gerenciamento do Banco de Dados
class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect('tasks.db', check_same_thread=False)
        self.init_db()

    def init_db(self):
        c = self.conn.cursor()
        # Tabela de usuários
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        ''')
        # Tabela de tarefas
        c.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT,
                cost REAL,
                due_date TEXT,
                display_order INTEGER,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        # Tabela de mensagens do chatbot
        c.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        self.conn.commit()

    def get_connection(self):
        return self.conn

# Classe para Gerenciamento de Usuários
class UserManager:
    def __init__(self, conn):
        self.conn = conn

    def register_user(self, username, password):
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            return False, "Nome de usuário já existe. Por favor, escolha outro."
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        self.conn.commit()
        return True, "Registro realizado com sucesso! Faça login."

    def login_user(self, username, password):
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        if user and hash_password(password) == user[2]:
            return True, user
        else:
            return False, "Credenciais inválidas."

# Classe para Gerenciamento de Tarefas
class TaskManager:
    def __init__(self, conn, user_id):
        self.conn = conn
        self.user_id = user_id

    def get_tasks(self):
        c = self.conn.cursor()
        c.execute("""
            SELECT id, task_name, cost, due_date, display_order FROM tasks
            WHERE user_id=?
            ORDER BY display_order
        """, (self.user_id,))
        return c.fetchall()

    def add_task(self, task_name, cost, due_date):
        c = self.conn.cursor()
        # Verificar se o nome da tarefa já existe
        c.execute("SELECT * FROM tasks WHERE task_name=? AND user_id=?", (task_name, self.user_id))
        if c.fetchone():
            return False, "Nome da tarefa já existe. Por favor, escolha outro nome."
        # Obter o maior display_order
        c.execute("SELECT MAX(display_order) FROM tasks WHERE user_id=?", (self.user_id,))
        max_order = c.fetchone()[0]
        if max_order is None:
            max_order = 0
        display_order = max_order + 1
        c.execute("""
            INSERT INTO tasks (task_name, cost, due_date, display_order, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (task_name, cost, due_date.strftime('%d/%m/%Y'), display_order, self.user_id))
        self.conn.commit()
        return True, "Tarefa adicionada com sucesso!"

    def update_task(self, task_id, task_name, cost, due_date):
        c = self.conn.cursor()
        # Verificar se o novo nome da tarefa já existe
        c.execute("SELECT * FROM tasks WHERE task_name=? AND user_id=? AND id<>?", (task_name, self.user_id, task_id))
        if c.fetchone():
            return False, "Nome da tarefa já existe. Por favor, escolha outro nome."
        c.execute("""
            UPDATE tasks SET task_name=?, cost=?, due_date=?
            WHERE id=? AND user_id=?
        """, (task_name, cost, due_date.strftime('%d/%m/%Y'), task_id, self.user_id))
        self.conn.commit()
        return True, "Tarefa atualizada com sucesso!"

    def delete_task(self, task_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, self.user_id))
        # Reordenar display_order
        c.execute("SELECT id FROM tasks WHERE user_id=? ORDER BY display_order", (self.user_id,))
        tasks = c.fetchall()
        for idx, t in enumerate(tasks):
            c.execute("UPDATE tasks SET display_order=? WHERE id=?", (idx+1, t[0]))
        self.conn.commit()
        return True, "Tarefa excluída com sucesso!"

    def move_task_up(self, task_id):
        c = self.conn.cursor()
        c.execute("SELECT display_order FROM tasks WHERE id=? AND user_id=?", (task_id, self.user_id))
        current_order = c.fetchone()[0]
        if current_order > 1:
            new_order = current_order - 1
            # Task above
            c.execute("SELECT id FROM tasks WHERE display_order=? AND user_id=?", (new_order, self.user_id))
            above_task_id = c.fetchone()[0]
            # Swap orders
            c.execute("UPDATE tasks SET display_order=? WHERE id=? AND user_id=?", (current_order, above_task_id, self.user_id))
            c.execute("UPDATE tasks SET display_order=? WHERE id=? AND user_id=?", (new_order, task_id, self.user_id))
            self.conn.commit()
            return True, "Tarefa movida para cima!"
        else:
            return False, "A tarefa já está no topo."

    def move_task_down(self, task_id):
        c = self.conn.cursor()
        c.execute("SELECT display_order FROM tasks WHERE id=? AND user_id=?", (task_id, self.user_id))
        current_order = c.fetchone()[0]
        # Get max order
        c.execute("SELECT MAX(display_order) FROM tasks WHERE user_id=?", (self.user_id,))
        max_order = c.fetchone()[0]
        if current_order < max_order:
            new_order = current_order + 1
            # Task below
            c.execute("SELECT id FROM tasks WHERE display_order=? AND user_id=?", (new_order, self.user_id))
            below_task_id = c.fetchone()[0]
            # Swap orders
            c.execute("UPDATE tasks SET display_order=? WHERE id=? AND user_id=?", (current_order, below_task_id, self.user_id))
            c.execute("UPDATE tasks SET display_order=? WHERE id=? AND user_id=?", (new_order, task_id, self.user_id))
            self.conn.commit()
            return True, "Tarefa movida para baixo!"
        else:
            return False, "A tarefa já está no final."

# Classe para Gerenciamento do Chatbot
class ChatbotManager:
    def __init__(self, conn, user_id):
        self.conn = conn
        self.user_id = user_id

    def get_messages(self):
        c = self.conn.cursor()
        c.execute("""
            SELECT role, content FROM messages
            WHERE user_id=?
            ORDER BY timestamp
        """, (self.user_id,))
        return c.fetchall()

    def add_message(self, role, content):
        c = self.conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("""
            INSERT INTO messages (user_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (self.user_id, role, content, timestamp))
        self.conn.commit()

    def clear_messages(self):
        c = self.conn.cursor()
        c.execute("DELETE FROM messages WHERE user_id=?", (self.user_id,))
        self.conn.commit()

# Função de Login
def login():
    st.title("🔐 Login")
    with st.form("login_form"):
        username = st.text_input("Nome de Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        if not username or not password:
            st.error("Por favor, preencha todos os campos.")
            return
        user_manager = UserManager(conn)
        success, result = user_manager.login_user(username, password)
        if success:
            st.session_state['logged_in'] = True
            st.session_state['user_id'] = result[0]
            st.session_state['username'] = result[1]
            st.success(f"Bem-vindo, {username}!")
            st.session_state['view'] = 'Lista de Tarefas'
        else:
            st.error(result)

# Função de Registro
def register():
    st.title("📝 Registro de Usuário")
    with st.form("register_form"):
        username = st.text_input("Nome de Usuário")
        password = st.text_input("Senha", type="password")
        confirm_password = st.text_input("Confirmar Senha", type="password")
        submitted = st.form_submit_button("Registrar")
    if submitted:
        if not username or not password or not confirm_password:
            st.error("Por favor, preencha todos os campos.")
            return
        if password != confirm_password:
            st.error("As senhas não coincidem.")
            return
        user_manager = UserManager(conn)
        success, message = user_manager.register_user(username, password)
        if success:
            st.success(message)
            st.session_state['view'] = 'Login'
        else:
            st.error(message)

# Função para exibir tarefas
def show_tasks(task_manager):
    st.title("📋 Lista de Tarefas")
    tasks = task_manager.get_tasks()
    if not tasks:
        st.info("Nenhuma tarefa encontrada. Adicione uma nova tarefa.")
    else:
        for idx, task in enumerate(tasks):
            task_id, task_name, cost, due_date, display_order = task
            task_container = st.container()
            is_high_cost = cost >= 1000.0
            container_style = "task-container"
            if is_high_cost:
                container_style += " highlight"
            with task_container:
                st.markdown(f"<div class='{container_style}'>", unsafe_allow_html=True)
                cols = st.columns([3, 2, 2, 1, 1, 1])
                cols[0].markdown(f"**{task_name}**")
                cols[1].markdown(f"Custo: R${cost:.2f}")
                cols[2].markdown(f"Data Limite: {due_date}")
                with cols[3]:
                    if idx > 0:
                        if cols[3].button("🔼", key=f"up_{task_id}"):
                            success, message = task_manager.move_task_up(task_id)
                            if success:
                                st.success(message)
                                st.session_state['view'] = 'Lista de Tarefas'
                            else:
                                st.error(message)
                with cols[4]:
                    if idx < len(tasks) - 1:
                        if cols[4].button("🔽", key=f"down_{task_id}"):
                            success, message = task_manager.move_task_down(task_id)
                            if success:
                                st.success(message)
                                st.session_state['view'] = 'Lista de Tarefas'
                            else:
                                st.error(message)
                with cols[5]:
                    if cols[5].button("✏️", key=f"edit_{task_id}"):
                        st.session_state["task_to_edit"] = task_id
                        st.session_state["view"] = "Editar Tarefa"
                    if cols[5].button("🗑️", key=f"delete_{task_id}"):
                        st.session_state["task_to_delete"] = task_id
                        st.session_state["view"] = "Excluir Tarefa"
                st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("➕ Incluir Nova Tarefa"):
        st.session_state['view'] = 'Incluir Tarefa'

# Função para adicionar tarefa
def add_task(task_manager):
    st.title("➕ Incluir Nova Tarefa")
    with st.form("add_task_form"):
        task_name = st.text_input("Nome da Tarefa")
        cost = st.number_input("Custo (R$)", min_value=0.0, step=0.01)
        due_date_str = st.text_input("Data Limite (dd/mm/aaaa)", value=date.today().strftime('%d/%m/%Y'))
        submitted = st.form_submit_button("Adicionar Tarefa")
    if submitted:
        if not task_name or not due_date_str:
            st.error("Por favor, preencha todos os campos.")
            return
        try:
            due_date = datetime.strptime(due_date_str, '%d/%m/%Y')
        except ValueError:
            st.error("Data inválida. Por favor, insira no formato dd/mm/aaaa.")
            return
        success, message = task_manager.add_task(task_name, cost, due_date)
        if success:
            st.success(message)
            st.session_state['view'] = 'Lista de Tarefas'
        else:
            st.error(message)

# Função para editar tarefa
def edit_task(task_manager):
    st.title("✏️ Editar Tarefa")
    task_id = st.session_state.get("task_to_edit")
    if not task_id:
        st.error("Nenhuma tarefa selecionada para editar.")
        st.session_state["view"] = "Lista de Tarefas"
        return
    tasks = task_manager.get_tasks()
    task = next((t for t in tasks if t[0] == task_id), None)
    if not task:
        st.error("Tarefa não encontrada.")
        st.session_state["view"] = "Lista de Tarefas"
        return
    task_name, cost, due_date = task[1], task[2], task[3]
    with st.form("edit_task_form"):
        new_task_name = st.text_input("Nome da Tarefa", value=task_name)
        new_cost = st.number_input("Custo (R$)", min_value=0.0, step=0.01, value=cost)
        new_due_date_str = st.text_input("Data Limite (dd/mm/aaaa)", value=due_date)
        submitted = st.form_submit_button("Atualizar Tarefa")
    if submitted:
        if not new_task_name or not new_due_date_str:
            st.error("Por favor, preencha todos os campos.")
            return
        try:
            new_due_date = datetime.strptime(new_due_date_str, '%d/%m/%Y')
        except ValueError:
            st.error("Data inválida. Por favor, insira no formato dd/mm/aaaa.")
            return
        success, message = task_manager.update_task(task_id, new_task_name, new_cost, new_due_date)
        if success:
            st.success(message)
            st.session_state['view'] = 'Lista de Tarefas'
        else:
            st.error(message)

# Função para excluir tarefa
def delete_task(task_manager):
    st.title("🗑️ Excluir Tarefa")
    task_id = st.session_state.get("task_to_delete")
    if not task_id:
        st.error("Nenhuma tarefa selecionada para excluir.")
        st.session_state["view"] = "Lista de Tarefas"
        return
    tasks = task_manager.get_tasks()
    task = next((t for t in tasks if t[0] == task_id), None)
    if not task:
        st.error("Tarefa não encontrada.")
        st.session_state["view"] = "Lista de Tarefas"
        return
    task_name = task[1]
    st.warning(f"Tem certeza que deseja excluir a tarefa '{task_name}'?")
    if st.button("Confirmar Exclusão"):
        success, message = task_manager.delete_task(task_id)
        if success:
            st.success(message)
            st.session_state['view'] = 'Lista de Tarefas'
        else:
            st.error(message)
    if st.button("Cancelar"):
        st.session_state['view'] = 'Lista de Tarefas'

# Função para gerar relatório
def generate_report(task_manager):
    st.title("📈 Gerar Relatório de Tarefas")
    tasks = task_manager.get_tasks()
    if not tasks:
        st.info("Nenhuma tarefa disponível para gerar relatório.")
        return
    task_options = {f"{task[1]} (ID: {task[0]})": task[0] for task in tasks}
    selected_task_ids = st.multiselect("Selecione as Tarefas para o Relatório", options=list(task_options.values()), format_func=lambda x: next((k for k, v in task_options.items() if v == x), ""))
    if st.button("Gerar Relatório"):
        if not selected_task_ids:
            st.error("Por favor, selecione pelo menos uma tarefa.")
            return
        selected_tasks = [task for task in tasks if task[0] in selected_task_ids]
        prompt = (
            "Você é um assistente responsável por gerar relatórios precisos e objetivos com base nos dados fornecidos. "
            "Utilize **apenas** as informações abaixo para criar o relatório. Não adicione informações ou detalhes que não estejam presentes nos dados.\n\n"
            "### Relatório de Tarefas\n\n"
        )
        for idx, task in enumerate(selected_tasks, start=1):
            prompt += f"**Tarefa {idx}:**\n"
            prompt += f"- **Nome da Tarefa:** {task[1]}\n"
            prompt += f"- **Custo:** R${task[2]:.2f}\n"
            prompt += f"- **Data Limite:** {task[3]}\n"
            prompt += f"- **Ordem de Apresentação:** {task[4]}\n\n"
        prompt += (
            "Com base nas informações acima, gere um relatório detalhado. Mantenha o relatório objetivo, "
            "evitando adicionar opiniões ou informações que não estejam presentes nos dados fornecidos. "
            "Estruture o relatório com cabeçalhos claros para cada tarefa e inclua uma visão geral no início."
        )
        try:
            with st.spinner("Gerando relatório..."):
                # Configurar o modelo Gemini
                model = genai.GenerativeModel("gemini-1.5-flash")
                # Gerar o conteúdo
                response = model.generate_content(prompt)
                report = response.text
                st.subheader("📝 Relatório Gerado")
                st.write(report)
        except Exception as e:
            st.error(f"Erro ao gerar o relatório: {e}")

# Função para conversar com a IA
def chat_with_ai(chatbot_manager):
    st.title("Fale com a IA 🤖")
    st.markdown("Converse com nossa inteligência artificial para tirar suas dúvidas ou obter conselhos!")

    # Exibir o histórico de mensagens
    messages = chatbot_manager.get_messages()
    for role, content in messages:
        if role == 'user':
            with st.chat_message("user"):
                st.write(content)
        else:
            with st.chat_message("assistant"):
                st.write(content)

    # Entrada de mensagem usando st.chat_input
    user_input = st.chat_input("Digite sua mensagem:")
    if user_input:
        # Adicionar a mensagem do usuário ao histórico
        chatbot_manager.add_message('user', user_input)
        with st.chat_message("user"):
            st.write(user_input)

        # Construir o prompt a partir do histórico de forma estruturada
        prompt = "Você é um assistente de inteligência artificial amigável e prestativo. Responda às perguntas do usuário de forma clara e concisa.\n\n"
        messages = chatbot_manager.get_messages()
        for role, content in messages:
            if role == 'user':
                prompt += f"Usuário: {content}\n"
            else:
                prompt += f"Assistente: {content}\n"
        prompt += "Assistente:"

        # Enviar o prompt ao modelo
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                try:
                    # Configurar o modelo Gemini
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    # Gerar o conteúdo
                    response = model.generate_content(prompt)
                    resposta_ia = response.text
                    if resposta_ia:
                        # Adicionar a resposta da IA ao histórico
                        chatbot_manager.add_message('assistant', resposta_ia)
                        st.write(resposta_ia)
                    else:
                        st.error("Não foi possível obter a resposta da IA.")
                except Exception as e:
                    st.error(f"Erro ao obter a resposta da IA: {e}")

    # Botão para limpar a conversa
    if st.button("Limpar Conversa"):
        chatbot_manager.clear_messages()
        st.success("Conversa limpa.")

# Função Principal
def main():
    global conn
    db_manager = DatabaseManager()
    conn = db_manager.get_connection()

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if 'view' not in st.session_state:
        st.session_state['view'] = 'Login'

    if st.session_state['logged_in']:
        # Usuário logado
        user_id = st.session_state['user_id']
        username = st.session_state['username']

        task_manager = TaskManager(conn, user_id)
        chatbot_manager = ChatbotManager(conn, user_id)

        with st.sidebar:
            st.image("https://via.placeholder.com/150x150.png?text=Tarefas", width=150)
            st.markdown(f"**Bem-vindo, {username}!**")
            escolha = option_menu(
                "Menu Principal",
                ["Lista de Tarefas", "Incluir Tarefa", "Gerar Relatório", "Fale com a IA", "Logout"],
                icons=["list-task", "plus", "file-earmark-text", "chat-dots", "box-arrow-right"],
                menu_icon="cast",
                default_index=0
            )
            # Atualizar a visualização somente se não estiver em ação de edição ou exclusão
            if st.session_state['view'] not in ["Editar Tarefa", "Excluir Tarefa"]:
                st.session_state['view'] = escolha

        if st.session_state['view'] == "Lista de Tarefas":
            show_tasks(task_manager)
        elif st.session_state['view'] == "Incluir Tarefa":
            add_task(task_manager)
        elif st.session_state['view'] == "Editar Tarefa":
            edit_task(task_manager)
        elif st.session_state['view'] == "Excluir Tarefa":
            delete_task(task_manager)
        elif st.session_state['view'] == "Gerar Relatório":
            generate_report(task_manager)
        elif st.session_state['view'] == "Fale com a IA":
            chat_with_ai(chatbot_manager)
        elif st.session_state['view'] == "Logout":
            st.session_state['logged_in'] = False
            st.session_state.pop('user_id', None)
            st.session_state.pop('username', None)
            st.success("Você saiu da sua conta.")
            st.session_state['view'] = 'Login'
    else:
        # Usuário não logado
        menu = ["Login", "Registrar"]
        escolha = option_menu(
            "Bem-vindo",
            menu,
            icons=['box-arrow-in-right', 'person-plus'],
            menu_icon="cast",
            default_index=0,
            orientation="horizontal"
        )
        st.session_state['view'] = escolha

        if st.session_state['view'] == "Login":
            login()
        elif st.session_state['view'] == "Registrar":
            register()

if __name__ == "__main__":
    main()
