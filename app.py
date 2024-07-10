from flask import Flask, render_template, request, url_for, flash, redirect
import stripe
import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import login_user, LoginManager, logout_user, current_user, login_required, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

CURRENT_YEAR = datetime.now().year
PRICE = 2

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///commerce.db'
db = SQLAlchemy(app)

login_manger = LoginManager()
login_manger.init_app(app)

order_ledger = db.Table('order_ledger',
                        db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                        db.Column('product_id', db.Integer, db.ForeignKey('product.id'))
                        )

shopping_cart = db.Table('shopping_cart',
                         db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                         db.Column('product_id', db.Integer, db.ForeignKey('product.id'))
                         )


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    ordered_products = db.relationship('Product', secondary=order_ledger,
                                       backref='orders')
    cart_products = db.relationship('Product', secondary=shopping_cart,
                                    backref='cart')

    def __repr__(self):
        return f'<User: {self.name}>'


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    image = db.Column(db.String(250), nullable=False)
    price = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<Product: {self.name}>'

stripe_keys = {
    'secret_key': os.environ['STRIPE_SECRET_KEY'],
    'publishable_key': os.environ['STRIPE_PUBLIC_KEY']
}

stripe.api_key = stripe_keys['secret_key']


@login_manger.user_loader
def user_loader(user_id):
    return db.session.get(User, int(user_id))


@app.route('/')
def home():
    result = db.session.execute(db.select(Product))
    products = result.scalars().all()
    print(products[0].orders)
    user = db.get_or_404(User, 1)
    # print(user.ordered_products[0].price)
    return render_template('index.html', current_year=CURRENT_YEAR,
                           products=products)


@app.route('/checkout/<int:price>')
def checkout(price):
    # product = db.get_or_404(Product, product_id)
    return render_template('checkout.html',
                           key=stripe_keys['publishable_key'], price=price,
                           current_year=CURRENT_YEAR)


@login_required
@app.route('/charge/<int:price>', methods=['POST'])
def charge(price):
    # product = db.get_or_404(Product, product_id)
    amount = price * 100
    product_names = [pr.name for pr in current_user.cart_products]
    product_description = ','.join(product_names)

    customer = stripe.Customer.create(
        email=current_user.email,
        source=request.form['stripeToken']
    )

    charge = stripe.Charge.create(
        customer=customer.id,
        amount=amount,
        currency='usd',
        description=product_description
    )

    print(charge.status)
    if charge.status == 'succeeded':
        for pr in current_user.cart_products:
            if pr not in current_user.ordered_products:
                current_user.ordered_products.append(pr)
        current_user.cart_products = []
        db.session.commit()
        return render_template('charge.html', amount=price,
                               current_year=CURRENT_YEAR)
    else:
        return {'Error': 'Payment was not successful'}


@app.route('/login', methods=['GET', 'POST'])
def login():
    users = User.query.all()
    if request.method == 'POST':
        print('Yes', 'Post')
        for cr_user in users:
            if request.form.get('email') == cr_user.email:
                if check_password_hash(cr_user.password, request.form.get('password')):
                    login_user(cr_user)
                    return redirect(url_for('user'))
                else:
                    flash('Password incorrect. Try again.')
                    return url_for('login', current_year=CURRENT_YEAR)
    elif current_user.is_authenticated:
        return redirect(url_for('user'))
    return render_template('login.html', current_year=CURRENT_YEAR)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        users = User.query.all()
        emails = [user.email for user in users]
        if request.form.get('email') not in emails:
            user = User(
                name=request.form.get('name'),
                email=request.form.get('email'),
                password=generate_password_hash(request.form.get('password'),
                                                method='scrypt', salt_length=8)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("You've already signed up with that email. Log in instead!")
            return redirect(url_for('login'))
    elif current_user.is_authenticated:
        return redirect(url_for('user'))
    return render_template('signup.html', current_year=CURRENT_YEAR)


@app.route('/user')
def user():
    if current_user.is_authenticated:
        return render_template('user.html', current_year=CURRENT_YEAR)
    else:
        return redirect(url_for('login'))


@app.route('/cart/<int:product_id>')
def add_product(product_id):
    product = db.get_or_404(Product, product_id)
    total_price = 0
    if current_user.is_authenticated:
        if product not in current_user.cart_products:
            current_user.cart_products.append(product)
            db.session.commit()
        for pr in current_user.cart_products:
            total_price += pr.price
        print(total_price)
        return render_template('shopping_cart.html', current_year=CURRENT_YEAR,
                               price=total_price)
    else:
        return redirect(url_for('login'))


@app.route('/<int:product_id>')
def remove_product(product_id):
    if current_user.is_authenticated:
        product = db.get_or_404(Product, product_id)
        current_user.cart_products.remove(product)
        db.session.commit()
        return redirect(url_for('home'))
    else:
        return redirect(url_for('login'))



@app.route('/cart')
def cart():
    price = 0
    if current_user.is_authenticated:
        for pr in current_user.cart_products:
            price += pr.price
        return render_template('shopping_cart.html', current_year=CURRENT_YEAR,
                               price=price)
    else:
        return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, port=5005, host='0.0.0.0')

