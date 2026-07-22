import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# --- NOVO IMPORT DO CLOUDINARY ---
import cloudinary
import cloudinary.uploader

app = Flask(__name__) 
app.config['SECRET_KEY'] = 'super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')

# --- CONFIGURAÇÃO DO CLOUDINARY ---
cloudinary.config(
    cloud_name = 'hko3ntds',
    api_key = '419489122199773',
    api_secret = 'zyjrwtQWqra7hsDxB3kHFK6aBD8'
)

# Mantido por segurança, caso decida voltar atrás
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 

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
    orders = db.relationship('Order', backref='user', lazy=True) 

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    descricao = db.Column(db.Text)
    preco = db.Column(db.Float) 
    imagens = db.Column(db.Text) 
    link_pagamento = db.Column(db.String(300)) # Atualizado para link_pagamento
    orders = db.relationship('Order', backref='product', lazy=True) 
    categoria = db.Column(db.String(50), nullable=False)
    destaque = db.Column(db.Boolean, default=False)
    video_url = db.Column(db.String(500))
    preco_antigo = db.Column(db.Float, nullable=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    status = db.Column(db.Integer, default=1)
    tamanho = db.Column(db.String(5))
    
# --- STATUS MAP ATUALIZADO ---
STATUS_MAP = {
    1: "Processando seu pagamento",
    2: "Pagamento feito",
    3: "Pedido em preparação",
    4: "Pedido a caminho",
    5: "Pedido entregue",
    6: "Compra cancelada"
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS PRINCIPAIS ---
@app.route('/')
def index():
    produtos = Product.query.all()
    return render_template('index.html', produtos=produtos)

@app.route('/produtos')
def produtos():
    produtos = Product.query.all()
    return render_template('produtos.html', produtos=produtos)

@app.route('/produto/<int:id>')
def detalhe_produto(id):
    produto = Product.query.get_or_404(id)
    return render_template('detalhe.html', produto=produto)

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
@app.route('/comprar/<int:product_id>', methods=['POST'])
@login_required
def comprar(product_id):
    tamanho_escolhido = request.form.get('tamanho', '')
    produto = Product.query.get_or_404(product_id)
    
    # Registra o pedido no banco de dados para o painel administrativo acompanhar
    novo_pedido = Order(user_id=current_user.id, product_id=produto.id, status=1, tamanho=tamanho_escolhido)
    db.session.add(novo_pedido)
    db.session.commit()
    
    # Se o produto tem um link de pagamento cadastrado, abre a página intermediária segura
    if produto.link_pagamento and produto.link_pagamento.strip() != "":
        link_final = produto.link_pagamento.strip()
        # Garante que o link tenha o https:// para o navegador não bloquear
        if not link_final.startswith('http://') and not link_final.startswith('https://'):
            link_final = 'https://' + link_final
        return render_template('pagamento_intermediario.html', link=link_final)
        
    return redirect(url_for('minhas_compras'))


@app.route('/admin/delete_order/<int:order_id>', methods=['POST'])
@login_required
def delete_order(order_id):
    if not current_user.is_admin:
        return "Acesso Negado", 403
        
    pedido = Order.query.get_or_404(order_id)
    db.session.delete(pedido)
    db.session.commit()
    
    flash('Pedido excluído com sucesso!')
    return redirect(url_for('admin_panel'))

@app.route('/minhas_compras')
@login_required
def minhas_compras():
    pedidos = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('minhas_compras.html', pedidos=pedidos, status_map=STATUS_MAP)

# --- ÁREA DO ADMIN ---
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return "Acesso Negado", 403
    usuarios = User.query.all()
    pedidos = Order.query.all()
    produtos = Product.query.all()
    return render_template('admin.html', usuarios=usuarios, pedidos=pedidos, produtos=produtos, status_map=STATUS_MAP)

@app.route('/admin/toggle_role/<int:user_id>')
@login_required
def toggle_role(user_id):
    if current_user.is_admin:
        user = User.query.get(user_id)
        if user.username != 'admin':
            user.is_admin = not user.is_admin
            db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_order/<int:order_id>/<int:new_status>')
@login_required
def update_order(order_id, new_status):
    if current_user.is_admin and 1 <= new_status <= 6:
        order = Order.query.get(order_id)
        order.status = new_status
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
        
    produto = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        produto.nome = request.form['nome']
        produto.preco = float(request.form['preco'].replace(',', '.'))
        
        preco_antigo_str = request.form.get('preco_antigo', '').strip()
        produto.preco_antigo = float(preco_antigo_str.replace(',', '.')) if preco_antigo_str else None
        
        produto.categoria = request.form['categoria']
        produto.descricao = request.form['descricao']
        produto.imagens = request.form['imagens']
        produto.video_url = request.form.get('video_url', '')
        produto.link_pagamento = request.form.get('link_pagamento', '') # Captura o link de pagamento na edição
        produto.destaque = True if request.form.get('destaque') else False
        
        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('admin_panel'))
        
    return render_template('edit_product.html', produto=produto)

@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        return "Acesso Negado", 403
        
    produto = Product.query.get_or_404(product_id)
    Order.query.filter_by(product_id=produto.id).delete()
    
    db.session.delete(produto)
    db.session.commit()
    
    flash('Produto excluído com sucesso!')
    return redirect(url_for('admin_panel'))

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return "Acesso Negado", 403

    if request.method == 'POST':
        nome = request.form['nome']
        descricao = request.form['descricao']
        
        preco = float(request.form['preco'].replace(',', '.')) 
        
        preco_antigo_str = request.form.get('preco_antigo', '').strip()
        preco_antigo = float(preco_antigo_str.replace(',', '.')) if preco_antigo_str else None

        video_url = request.form.get('video_url', '')
        link_pagamento = request.form.get('link_pagamento', '') # <- CORRIGIDO: Captura correta do link do PagBank
        
        categoria = request.form.get('categoria')
        destaque = True if request.form.get('destaque') == 'on' else False

        fotos = request.files.getlist('fotos')
        caminhos_fotos = []

        for foto in fotos:
            if foto.filename != '':
                upload_result = cloudinary.uploader.upload(foto)
                url_da_imagem = upload_result['secure_url']
                caminhos_fotos.append(url_da_imagem)

        imagens_str = ",".join(caminhos_fotos)

        novo_produto = Product(
            nome=nome, 
            descricao=descricao, 
            preco=preco, 
            preco_antigo=preco_antigo,  
            imagens=imagens_str, 
            video_url=video_url,
            categoria=categoria,
            link_pagamento=link_pagamento, # <- CORRIGIDO: Passado corretamente para o banco
            destaque=destaque
        )
        
        db.session.add(novo_produto)
        db.session.commit()

        return redirect(url_for('admin_panel'))

    return render_template('add_product.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', password=generate_password_hash('admin', method='pbkdf2:sha256'), is_admin=True)
            db.session.add(admin_user)
            db.session.commit()
    app.run(debug=True)
