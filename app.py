import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loja.db'

# --- NOVA CONFIGURAÇÃO PARA UPLOAD DE FOTOS ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Cria a pasta automaticamente se não existir

db = SQLAlchemy(app)
with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS DE BANCO DE DADOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(150))
    endereco = db.Column(db.String(250))
    bairro = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='user', lazy=True) # Adicione isso

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    descricao = db.Column(db.Text)
    preco = db.Column(db.Float) # NOVO: Campo de Preço
    imagens = db.Column(db.Text) # NOVO: Salvará os caminhos das fotos separados por vírgula
    link_externo = db.Column(db.String(300))
    orders = db.relationship('Order', backref='product', lazy=True) # Adicione isso

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    status = db.Column(db.Integer, default=1) # 1 a 5

STATUS_MAP = {
    1: "Processando seu pagamento",
    2: "Pagamento feito",
    3: "Pedido em preparação",
    4: "Pedido a caminho",
    5: "Pedido entregue"
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS PRINCIPAIS ---
@app.route('/')
def index():
    # Simulando produtos cadastrados para o carrosel
    produtos = Product.query.all()
    return render_template('index.html', produtos=produtos)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hash_senha = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        novo_usuario = User(
            nome_completo=request.form['nome'],
            endereco=request.form['endereco'],
            bairro=request.form['bairro'],
            telefone=request.form['telefone'],
            username=request.form['username'],
            password=hash_senha
        )
        db.session.add(novo_usuario)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Usuário ou senha incorretos.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- ÁREA DO CLIENTE ---
@app.route('/comprar/<int:product_id>')
@login_required
def comprar(product_id):
    produto = Product.query.get_or_404(product_id)
    # Registra o pedido
    novo_pedido = Order(user_id=current_user.id, product_id=produto.id, status=1)
    db.session.add(novo_pedido)
    db.session.commit()
    
    # Renderiza uma página intermediária em vez de redirecionar direto
    return render_template('pagamento_intermediario.html', link=produto.link_externo)

@app.route('/minhas_compras')
@login_required
def minhas_compras():
    pedidos = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('compras.html', pedidos=pedidos, status_map=STATUS_MAP)

# --- ÁREA DO ADMIN ---
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Acesso Negado", 403
    usuarios = User.query.all()
    pedidos = Order.query.all()
    return render_template('admin.html', usuarios=usuarios, pedidos=pedidos, status_map=STATUS_MAP)

@app.route('/admin/toggle_role/<int:user_id>')
@login_required
def toggle_role(user_id):
    if current_user.is_admin:
        user = User.query.get(user_id)
        if user.username != 'admin': # Protege o admin principal
            user.is_admin = not user.is_admin
            db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_order/<int:order_id>/<int:new_status>')
@login_required
def update_order(order_id, new_status):
    if current_user.is_admin and 1 <= new_status <= 5:
        order = Order.query.get(order_id)
        order.status = new_status
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return "Acesso Negado", 403

    if request.method == 'POST':
        nome = request.form['nome']
        descricao = request.form['descricao']
        # Substitui vírgula por ponto caso o admin digite "199,90" ao invés de "199.90"
        preco = float(request.form['preco'].replace(',', '.')) 
        link_externo = request.form['link_externo']

        # Recebe a lista de fotos enviadas
        fotos = request.files.getlist('fotos')
        caminhos_fotos = []

        for foto in fotos:
            if foto.filename != '':
                filename = secure_filename(foto.filename)
                # Salva a foto na pasta static/uploads
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                foto.save(caminho_salvar)
                # Guarda o caminho para usar no HTML (com a barra invertida ajustada para web)
                caminhos_fotos.append(f"/{caminho_salvar}".replace("\\", "/"))

        # Junta todos os caminhos em uma única string separada por vírgulas
        imagens_str = ",".join(caminhos_fotos)

        novo_produto = Product(nome=nome, descricao=descricao, preco=preco, imagens=imagens_str, link_externo=link_externo)
        db.session.add(novo_produto)
        db.session.commit()

        return redirect(url_for('admin_panel'))

    return render_template('add_product.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Cria o admin padrão caso não exista
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', password=generate_password_hash('admin', method='pbkdf2:sha256'), is_admin=True)
            db.session.add(admin_user)
            db.session.commit()
    app.run(debug=True)
