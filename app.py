import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image  

# 🚨 관리자 이메일 설정
ADMIN_EMAILS = ['seohyohoon@ps.hs.kr', 'admin@test.com']

app = Flask(__name__)
app.secret_key = 'super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///lost_found.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

with app.app_context():
    try:
        db.create_all()
        print("데이터베이스 테이블 생성 성공!")
    except Exception as e:
        print(f"테이블 생성 중 오류 발생: {e}")

# 폴더 생성
os.makedirs('static/uploads', exist_ok=True)

# --- 데이터베이스 모델 ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), default='student')

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    category = db.Column(db.String(50), default='기타') 
    status = db.Column(db.String(20), default='보관중') 
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    user_name = db.Column(db.String(50), nullable=False)
    pickup_time = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='대기중')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    author_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, nullable=False) 
    image_path = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    dropoff_time = db.Column(db.String(100), nullable=False) 
    status = db.Column(db.String(20), default='확인 대기')
    date_reported = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 유틸리티 함수 ---
@app.context_processor
def inject_unread_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return dict(unread_notifs=count)
    return dict(unread_notifs=0)

def notify_admin(message, link):
    admins = User.query.filter(User.email.in_(ADMIN_EMAILS)).all()
    for admin in admins:
        db.session.add(Notification(user_id=admin.id, message=message, link=link))

def notify_user(user_id, message, link):
    db.session.add(Notification(user_id=user_id, message=message, link=link))

def optimize_and_save_image(file, save_path):
    img = Image.open(file)
    if img.mode != 'RGB': img = img.convert('RGB')
    img.thumbnail((800, 800)) 
    img.save(save_path, format='JPEG', quality=85)

# --- 라우트 (페이지) ---

@app.route('/')
def home():
    if current_user.is_authenticated: return redirect(url_for('board'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        if User.query.filter_by(email=email).first():
            flash('이미 존재하는 이메일입니다.')
            return redirect(url_for('signup'))
        new_user = User(
            email=email, 
            password=generate_password_hash(request.form.get('password')), 
            student_id=request.form.get('student_id'), 
            name=request.form.get('name')
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('board'))
        flash('이메일이나 비밀번호가 틀렸습니다.')
    return render_template('login.html')

# 🚨 신규 추가: 비밀번호 재설정 (본인 인증 방식)
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        name = request.form.get('name').strip()
        student_id = request.form.get('student_id').strip()
        new_password = request.form.get('new_password')
        
        user = User.query.filter_by(email=email, name=name, student_id=student_id).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요!')
            return redirect(url_for('login'))
        flash('정보가 일치하는 학생이 없습니다.')
    return render_template('reset_password.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/board')
@login_required
def board():
    search_word = request.args.get('q', '')
    category = request.args.get('category', '전체') 
    page = request.args.get('page', 1, type=int)
    query = Item.query.order_by(Item.date_posted.desc())
    if search_word: query = query.filter(Item.description.contains(search_word))
    if category != '전체': query = query.filter(Item.category == category)
    pagination = query.paginate(page=page, per_page=8, error_out=False)
    return render_template('board.html', items=pagination.items, pagination=pagination, search_word=search_word, category=category, admin_emails=ADMIN_EMAILS)

@app.route('/item/<int:item_id>')
@login_required
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    comments = Comment.query.filter_by(item_id=item_id).order_by(Comment.date_posted.asc()).all()
    return render_template('item_detail.html', item=item, comments=comments, admin_emails=ADMIN_EMAILS)

@app.route('/add_item', methods=['GET', 'POST'])
@login_required 
def add_item():
    if current_user.email not in ADMIN_EMAILS: return redirect(url_for('board'))
    if request.method == 'POST':
        file = request.files.get('image')
        if file:
            save_name = datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(file.filename)
            filepath = os.path.join('static/uploads', save_name)
            optimize_and_save_image(file, filepath)
            db.session.add(Item(image_path=save_name, description=request.form.get('description'), category=request.form.get('category')))
            db.session.commit()
            return redirect(url_for('board'))
    return render_template('add_item.html')

# (나머지 기능들: claim, report, notifications, mypage 등은 기존과 동일)
@app.route('/claim/<int:item_id>', methods=['GET', 'POST'])
@login_required
def claim(item_id):
    item = Item.query.get_or_404(item_id)
    if request.method == 'POST':
        db.session.add(Claim(item_id=item.id, user_id=current_user.id, student_id=current_user.student_id, user_name=current_user.name, pickup_time=request.form.get('pickup_time')))
        item.status = '확인 중'
        notify_admin(f"{current_user.name} 학생이 분실물을 신청했습니다!", url_for('admin_dashboard'))
        db.session.commit()
        return redirect(url_for('mypage'))
    return render_template('claim.html', item=item)

@app.route('/report', methods=['GET', 'POST'])
@login_required
def report_item():
    if current_user.email in ADMIN_EMAILS: return redirect(url_for('board'))
    if request.method == 'POST':
        file = request.files.get('image')
        save_name = None
        if file:
            save_name = "report_" + datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(file.filename)
            optimize_and_save_image(file, os.path.join('static/uploads', save_name))
        db.session.add(Report(author_name=current_user.name, user_id=current_user.id, image_path=save_name, description=request.form.get('description'), location=request.form.get('location'), dropoff_time=request.form.get('dropoff_time')))
        notify_admin("새로운 습득물 제보가 도착했습니다!", url_for('admin_reports'))
        db.session.commit()
        return redirect(url_for('board'))
    return render_template('report.html')

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if current_user.email not in ADMIN_EMAILS: return redirect(url_for('board'))
    claims = Claim.query.order_by(Claim.id.desc()).all()
    item_dict = {item.id: item for item in Item.query.all()}
    return render_template('admin.html', claims=claims, item_dict=item_dict)

@app.route('/admin_reports')
@login_required
def admin_reports():
    if current_user.email not in ADMIN_EMAILS: return redirect(url_for('board'))
    return render_template('admin_reports.html', reports=Report.query.all())

@app.route('/mypage')
@login_required
def mypage():
    claims = Claim.query.filter_by(user_id=current_user.id).all()
    item_dict = {item.id: item for item in Item.query.all()}
    return render_template('mypage.html', claims=claims, item_dict=item_dict)

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.id.desc()).all()
    for n in notifs: n.is_read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)

@app.route('/add_comment/<int:item_id>', methods=['POST'])
@login_required
def add_comment(item_id):
    content = request.form.get('content')
    author = "관리자" if current_user.email in ADMIN_EMAILS else current_user.name
    db.session.add(Comment(item_id=item_id, author_name=author, content=content))
    db.session.commit()
    return redirect(url_for('item_detail', item_id=item_id))

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    if current_user.email in ADMIN_EMAILS:
        Item.query.filter_by(id=item_id).delete()
        db.session.commit()
    return redirect(url_for('board'))

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)