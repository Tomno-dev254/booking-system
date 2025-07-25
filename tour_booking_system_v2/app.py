import os
import sqlite3
import functools
from datetime import datetime
import requests # New: For M-Pesa API calls
import json     # New: For M-Pesa API calls
import base64   # New: For M-Pesa API calls
from PIL import Image # For image processing (good to keep)
import uuid # For unique filenames

from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify # jsonify is new
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from tour_booking_system_v2 import create_app


# Flask-Mail (Keep this as you're using it for emails)
from flask_mail import Mail, Message

# Import database functions (assuming database.py handles get_db, close_db, init_app)
from .database import get_db, close_db, init_app


# Load environment variables from .env file (must be at the top)
load_dotenv()

# --- M-PESA API Global Configuration ---
# These are loaded once when the app starts.
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET')
MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE')
MPESA_PASSKEY = os.getenv('MPESA_PASSKEY')
MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL') # From .env, updated by ngrok

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Configure Flask app
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'a_fallback_secret_key_if_env_fails'),
        DATABASE=os.path.join(app.instance_path, 'tour_booking.db'),

        # --- Flask-Mail Configuration ---
        MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
        MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
        MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True').lower() == 'true',
        MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'False').lower() == 'true',
        MAIL_USERNAME=os.getenv('EMAIL_USER'),
        MAIL_PASSWORD=os.getenv('EMAIL_PASS'),
        MAIL_DEFAULT_SENDER=os.getenv('SENDGRID_SENDER_EMAIL', os.getenv('EMAIL_USER')),
    )

    # Initialize Flask-Mail
    mail = Mail(app)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    init_app(app) # Initialize database commands for Flask CLI

    # --- Authentication Helper Functions ---
    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        if user_id is None:
            g.user = None
        else:
            g.user = get_db().execute(
                'SELECT * FROM users WHERE id = ?', (user_id,)
            ).fetchone()

    def login_required(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash('You need to be logged in to access this page.', 'warning')
                return redirect(url_for('login'))
            return view(**kwargs)
        return wrapped_view

    def admin_required(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash('You need to be logged in to access this page.', 'warning')
                return redirect(url_for('login'))
            if g.user['is_admin'] != 1:
                flash('You do not have administrative privileges.', 'danger')
                return redirect(url_for('index'))
            return view(**kwargs)
        return wrapped_view

    # --- Email Sending Functions (Flask-Mail) ---
    def send_confirmation_email(recipient_email, recipient_name, tour_name, num_participants, booking_id):
        sender_email = app.config.get('MAIL_DEFAULT_SENDER')

        if not sender_email or not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            app.logger.warning("Flask-Mail configuration incomplete. Confirmation email not sent.")
            return False

        try:
            msg = Message(
                subject=f'Tour Booking Confirmation: {tour_name}',
                sender=sender_email,
                recipients=[recipient_email],
                html=f'''
                <p>Hello {recipient_name},</p>
                <p>Your booking for the <strong>{tour_name}</strong> tour has been confirmed!</p>
                <p><strong>Booking ID:</strong> {booking_id}</p>
                <p><strong>Number of Participants:</strong> {num_participants}</p>
                <p>Thank you for choosing our tour booking system.</p>
                <p>Best regards,<br>The Tour Booking Team</p>
                '''
            )
            mail.send(msg)
            app.logger.info(f"Confirmation email sent to {recipient_email}.")
            return True
        except Exception as e:
            app.logger.error(f"Error sending confirmation email to {recipient_email}: {e}")
            return False

    def send_contact_email(name, email, subject, message_body):
        admin_email_recipient = os.getenv('ADMIN_EMAIL_FOR_CONTACT', 'your_admin_inbox@example.com')
        sender_email = app.config.get('MAIL_DEFAULT_SENDER')

        if not sender_email or not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            app.logger.warning("Flask-Mail configuration incomplete. Contact email not sent.")
            return False

        try:
            msg = Message(
                subject=f"New Contact Form: {subject} (from {name} - {email})",
                sender=sender_email,
                recipients=[admin_email_recipient],
                html=f'''
                <p>You have received a new message from your website's contact form:</p>
                <p><strong>Name:</strong> {name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Subject:</strong> {subject}</p>
                <p><strong>Message:</strong></p>
                <p style="white-space: pre-wrap;">{message_body}</p>
                '''
            )
            mail.send(msg)
            app.logger.info(f"Contact email sent from {email} to {admin_email_recipient}.")
            return True
        except Exception as e:
            app.logger.error(f"Error sending contact email from {email}: {e}")
            return False

    # --- M-Pesa Specific Helper Function ---
    def get_mpesa_access_token():
        try:
            consumer_key = MPESA_CONSUMER_KEY
            consumer_secret = MPESA_CONSUMER_SECRET
            # Use sandbox URL for development
            api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            # For production: "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

            response = requests.get(api_url, auth=(consumer_key, consumer_secret))
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()['access_token']
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error getting M-Pesa access token: {e}")
            return None

    # --- Core Routes ---
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/register', methods=('GET', 'POST'))
    def register():
        if request.method == 'POST':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            confirm_password = request.form['confirm_password']
            db = get_db()
            error = None

            if not username:
                error = 'Username is required.'
            elif not email:
                error = 'Email is required.'
            elif '@' not in email or '.' not in email:
                error = 'Please enter a valid email address.'
            elif not password:
                error = 'Password is required.'
            elif password != confirm_password:
                error = 'Passwords do not match.'
            elif db.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone() is not None:
                error = f"User {username} is already registered."
            elif db.execute(
                'SELECT id FROM users WHERE email = ?', (email,)
            ).fetchone() is not None:
                error = f"An account with email {email} already exists."

            if error is None:
                try:
                    db.execute(
                        'INSERT INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)',
                        (username, email, generate_password_hash(password), 0)
                    )
                    db.commit()
                    flash('Registration successful! Please log in.', 'success')
                    return redirect(url_for('login'))
                except sqlite3.Error as e:
                    db.rollback()
                    error = f"Database error: {e}"
            flash(error, 'error')
        return render_template('register.html')

    @app.route('/login', methods=('GET', 'POST'))
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            db = get_db()
            error = None
            user = db.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            ).fetchone()

            if user is None:
                error = 'Incorrect username.'
            elif not check_password_hash(user['password'], password):
                error = 'Incorrect password.'

            if error is None:
                session.clear()
                session['user_id'] = user['id']
                flash(f'Welcome back, {user["username"]}!', 'success')
                return redirect(url_for('index'))
            flash(error, 'error')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index'))

    @app.route('/tours')
    def tours():
        db = get_db()
        available_tours = db.execute(
            "SELECT * FROM tours WHERE status = 'available' ORDER BY date ASC"
        ).fetchall()
        return render_template('tours.html', tours=available_tours)

    # --- MODIFIED: Booking flow to initiate M-Pesa payment ---
    @app.route('/book/<int:tour_id>', methods=('GET', 'POST'))
    @login_required
    def book_tour(tour_id):
        db = get_db()
        tour = db.execute('SELECT * FROM tours WHERE id = ?', (tour_id,)).fetchone()

        if tour is None or tour['status'] != 'available':
            flash('Tour not found or not available for booking.', 'error')
            return redirect(url_for('tours'))

        if request.method == 'POST':
            num_participants = int(request.form['num_participants'])
            customer_name = g.user['username']
            customer_email = g.user['email']

            if num_participants <= 0:
                flash('Please ensure participants are greater than 0.', 'error')
                return render_template('book_tour.html', tour=tour)

            if tour['current_participants'] + num_participants > tour['max_participants']:
                flash(f'Sorry, there are only {tour["max_participants"] - tour["current_participants"]} spots left for this tour.', 'error')
                return render_template('book_tour.html', tour=tour)

            try:
                # Insert booking as 'pending' before M-Pesa payment
                cursor = db.execute(
                    'INSERT INTO bookings (tour_id, user_id, customer_name, customer_email, num_participants, payment_status) VALUES (?, ?, ?, ?, ?, ?)',
                    (tour_id, g.user['id'], customer_name, customer_email, num_participants, 'pending')
                )
                booking_id = cursor.lastrowid # Get the ID of the newly inserted booking
                db.commit()
                flash('Booking placed successfully! Proceed to payment.', 'success')
                # Redirect to a new booking_details page to initiate M-Pesa
                return redirect(url_for('booking_details', booking_id=booking_id))
            except sqlite3.Error as e:
                db.rollback()
                flash(f'Database error during booking: {e}', 'danger')
                app.logger.error(f"Error creating booking: {e}")
            finally:
                pass # get_db handles closing connection implicitly at end of request

        return render_template('book_tour.html', tour=tour)

    # --- NEW: Booking Details (before payment) ---
    @app.route('/booking_details/<int:booking_id>')
    @login_required
    def booking_details(booking_id):
        db = get_db()
        booking = db.execute(
            'SELECT b.id, b.num_participants, b.payment_status, b.booking_date, '
            'b.customer_name, b.customer_email, '
            'b.mpesa_receipt, b.amount_paid, b.phone_number_paid, ' # Include M-Pesa specific fields
            't.name AS tour_name, t.description, t.price, t.date AS tour_date '
            'FROM bookings b JOIN tours t ON b.tour_id = t.id '
            'WHERE b.id = ? AND b.user_id = ?',
            (booking_id, session['user_id'])
        ).fetchone()

        if not booking:
            flash('Booking not found or you do not have permission.', 'danger')
            return redirect(url_for('my_bookings')) # Assuming you have a my_bookings route

        return render_template('booking_details.html', booking=booking)

    # --- NEW: M-Pesa Payment Initiation Route (STK Push) ---
    @app.route('/initiate-mpesa-payment/<int:booking_id>', methods=['POST'])
    @login_required
    def initiate_mpesa_payment(booking_id):
        phone_number = request.form.get('phone_number')

        # Basic validation for phone number format
        if not phone_number or not phone_number.isdigit() or len(phone_number) < 9:
            flash('Please enter a valid M-Pesa phone number (e.g., 07XXXXXXXX or 2547XXXXXXXX).', 'danger')
            return redirect(url_for('booking_details', booking_id=booking_id))

        db = get_db()
        booking = db.execute(
            'SELECT b.id, b.num_participants, b.payment_status, t.price, t.name AS tour_name '
            'FROM bookings b JOIN tours t ON b.tour_id = t.id WHERE b.id = ? AND b.user_id = ?',
            (booking_id, session['user_id'])
        ).fetchone()

        if not booking:
            flash('Booking not found or you do not have permission.', 'danger')
            return redirect(url_for('my_bookings'))

        if booking['payment_status'] == 'paid':
            flash('This booking has already been paid for.', 'info')
            return redirect(url_for('booking_details', booking_id=booking_id))

        try:
            # Calculate total amount (M-Pesa expects whole numbers in KES)
            amount = int(booking['price'] * booking['num_participants'])
            
            # Format phone number to 2547XXXXXXXX
            if phone_number.startswith('0'):
                phone_number = '254' + phone_number[1:]
            elif len(phone_number) == 9 and phone_number.startswith(('7', '1')):
                phone_number = '254' + phone_number
            elif not phone_number.startswith('254'):
                flash('Phone number must start with 07, 01, or 254.', 'danger')
                return redirect(url_for('booking_details', booking_id=booking_id))

            access_token = get_mpesa_access_token()
            if not access_token:
                flash('Could not get M-Pesa access token. Please try again later.', 'danger')
                return redirect(url_for('booking_details', booking_id=booking_id))

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode('utf-8')

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            transaction_desc = f"Payment for {booking['tour_name']} booking {booking['id']}"
            
            payload = {
                "BusinessShortCode": MPESA_SHORTCODE,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline", # Use "CustomerPayBillOnline" for Paybill, "CustomerBuyGoodsOnline" for Till Number
                "Amount": amount,
                "PartyA": phone_number,
                "PartyB": MPESA_SHORTCODE,
                "PhoneNumber": phone_number,
                "CallBackURL": MPESA_CALLBACK_URL,
                "AccountReference": str(booking_id), # Unique reference for your transaction
                "TransactionDesc": transaction_desc
            }

            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

            response = requests.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()

            if response_data.get('ResponseCode') == '0':
                flash(f'M-Pesa STK Push initiated to {phone_number}. Please enter your M-Pesa PIN to complete payment.', 'info')
                return redirect(url_for('booking_details', booking_id=booking_id))
            else:
                app.logger.error(f"M-Pesa STK Push failed: {response_data.get('ResponseDescription', 'No description')} | ErrorCode: {response_data.get('ErrorCode')}")
                flash(f"M-Pesa payment initiation failed: {response_data.get('ResponseDescription', 'An unknown error occurred.')}", 'danger')
                return redirect(url_for('booking_details', booking_id=booking_id))

        except requests.exceptions.RequestException as e:
            app.logger.error(f"HTTP Request error during M-Pesa STK Push: {e}", exc_info=True)
            flash(f'An error occurred while initiating M-Pesa payment (network issue). Please try again.', 'danger')
            return redirect(url_for('booking_details', booking_id=booking_id))
        except Exception as e:
            app.logger.error(f"General error during M-Pesa STK Push: {e}", exc_info=True)
            flash(f'An unexpected error occurred. Please try again.', 'danger')
            return redirect(url_for('booking_details', booking_id=booking_id))

    # --- NEW: M-Pesa Callback (Webhook) Endpoint ---
    @app.route('/mpesa-callback', methods=['POST'])
    def mpesa_callback():
        data = request.json
        app.logger.info(f"M-Pesa Callback Received: {json.dumps(data, indent=2)}")

        # Acknowledge receipt immediately as per Daraja API best practices
        response_to_daraja = {"ResultCode": 0, "ResultDesc": "C2B Recieved."}

        try:
            body = data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc')

            callback_metadata = stk_callback.get('CallbackMetadata', {})
            item_list = callback_metadata.get('Item', [])
            
            booking_id_str = None # Received as string
            mpesa_receipt_number = None
            amount_paid = None
            phone_number = None

            # Parse the CallbackMetadata to get transaction details
            for item in item_list:
                if item.get('Name') == 'Amount':
                    amount_paid = item.get('Value')
                elif item.get('Name') == 'MpesaReceiptNumber':
                    mpesa_receipt_number = item.get('Value')
                elif item.get('Name') == 'PhoneNumber':
                    phone_number = item.get('Value')
                elif item.get('Name') == 'BillAccountRef': # This is where AccountReference (your booking_id) is usually found
                    booking_id_str = item.get('Value')

            conn = get_db() # Use get_db()
            booking_id = None
            if booking_id_str:
                try:
                    booking_id = int(booking_id_str) # Convert to int
                except ValueError:
                    app.logger.error(f"Invalid booking_id_str received: {booking_id_str}")
                    return jsonify({"ResultCode": 1, "ResultDesc": "Invalid Booking ID in callback."}), 200

            if result_code == 0: # Payment successful
                if booking_id:
                    try:
                        # Update booking status, mpesa_receipt, amount_paid, phone_number_paid
                        conn.execute('UPDATE bookings SET payment_status = ?, mpesa_receipt = ?, amount_paid = ?, phone_number_paid = ? WHERE id = ?',
                                    ('paid', mpesa_receipt_number, amount_paid, phone_number, booking_id))

                        # Also update tour's current_participants
                        booking_data = conn.execute('SELECT tour_id, num_participants FROM bookings WHERE id = ?', (booking_id,)).fetchone()
                        if booking_data:
                            conn.execute('UPDATE tours SET current_participants = current_participants + ? WHERE id = ?',
                                        (booking_data['num_participants'], booking_data['tour_id']))
                        
                        conn.commit()
                        app.logger.info(f"Booking {booking_id} updated to 'paid' via M-Pesa webhook. Receipt: {mpesa_receipt_number}")

                        # Optionally, send confirmation email here for paid bookings
                        booking_full_data = conn.execute(
                            'SELECT b.customer_email, b.customer_name, b.num_participants, t.name AS tour_name '
                            'FROM bookings b JOIN tours t ON b.tour_id = t.id WHERE b.id = ?',
                            (booking_id,)
                        ).fetchone()
                        if booking_full_data:
                            send_confirmation_email(
                                booking_full_data['customer_email'],
                                booking_full_data['customer_name'],
                                booking_full_data['tour_name'],
                                booking_full_data['num_participants'],
                                booking_id
                            )

                    except sqlite3.Error as e:
                        app.logger.error(f"DB Error updating booking {booking_id} via M-Pesa webhook: {e}")
                        conn.rollback()
                        response_to_daraja = {"ResultCode": 1, "ResultDesc": f"DB Error: {e}"}
                else:
                    app.logger.warning(f"Successful M-Pesa callback but booking_id not found in metadata: {data}")
                    response_to_daraja = {"ResultCode": 1, "ResultDesc": "Booking ID missing from callback metadata."}
            else: # Payment failed or cancelled by user
                if booking_id:
                    try:
                        # Update only payment_status for failed transactions
                        conn.execute('UPDATE bookings SET payment_status = ? WHERE id = ?', ('failed', booking_id))
                        conn.commit()
                        app.logger.warning(f"Booking {booking_id} M-Pesa payment failed. ResultCode: {result_code}, Desc: {result_desc}")
                    except sqlite3.Error as e:
                        app.logger.error(f"DB Error updating failed M-Pesa booking {booking_id}: {e}")
                        conn.rollback()
                        response_to_daraja = {"ResultCode": 1, "ResultDesc": f"DB Error on failed payment: {e}"}
                else:
                    app.logger.warning(f"Failed M-Pesa callback but booking_id not found: {data}")
                    response_to_daraja = {"ResultCode": 1, "ResultDesc": "Booking ID missing from failed callback."}

            return jsonify(response_to_daraja), 200

        except Exception as e:
            app.logger.error(f"Error processing M-Pesa callback: {e}", exc_info=True)
            response_to_daraja = {"ResultCode": 1, "ResultDesc": f"Internal Server Error: {e}"}
            return jsonify(response_to_daraja), 500

    # --- MODIFIED: Renamed from booking_success to booking_confirmed ---
    @app.route('/booking-confirmed/<int:booking_id>')
    @login_required
    def booking_confirmed(booking_id):
        db = get_db()
        booking = db.execute(
            'SELECT b.id, b.num_participants, b.payment_status, b.booking_date, '
            'b.customer_name, b.customer_email, '
            'b.mpesa_receipt, b.amount_paid, b.phone_number_paid, ' # Include M-Pesa specific fields
            't.name AS tour_name, t.description, t.price, t.date AS tour_date '
            'FROM bookings b JOIN tours t ON b.tour_id = t.id '
            'WHERE b.id = ? AND b.user_id = ?',
            (booking_id, session['user_id'])
        ).fetchone()

        if not booking:
            flash('Booking not found or you do not have permission.', 'danger')
            return redirect(url_for('my_bookings'))

        customer_name = booking['customer_name']
        num_participants = booking['num_participants']
        tour_name = booking['tour_name']
        
        flash('Your booking has been successfully placed!', 'success')
        return render_template(
            'success_booking.html', # This template expects these exact variables
            customer_name=customer_name,
            num_participants=num_participants,
            tour_name=tour_name
        )
    
    # --- NEW: My Bookings page to view status ---
    @app.route('/my_bookings')
    @login_required
    def my_bookings():
        db = get_db()
        user_bookings = db.execute(
            'SELECT b.id, b.num_participants, b.booking_date, b.payment_status, '
            't.name AS tour_name, t.price AS tour_price, t.date AS tour_date '
            'FROM bookings b JOIN tours t ON b.tour_id = t.id '
            'WHERE b.user_id = ? ORDER BY b.booking_date DESC',
            (g.user['id'],)
        ).fetchall()
        return render_template('my_bookings.html', bookings=user_bookings)

    # --- Content Pages ---
    @app.route('/coming_soon')
    def coming_soon():
        db = get_db()
        upcoming_tours = db.execute(
            "SELECT * FROM tours WHERE status = 'coming_soon' ORDER BY date ASC"
        ).fetchall()
        return render_template('coming_soon.html', tours=upcoming_tours)

    @app.route('/done_tours')
    def done_tours():
        db = get_db()
        past_tours = db.execute(
            "SELECT * FROM tours WHERE status = 'done' ORDER BY date DESC"
        ).fetchall()
        return render_template('done_tours.html', tours=past_tours)

    @app.route('/memories')
    def memories():
        db = get_db()
        all_memories = db.execute(
            "SELECT m.*, t.name AS tour_name FROM memories m LEFT JOIN tours t ON m.tour_id = t.id ORDER BY memory_date DESC"
        ).fetchall()
        return render_template('memories.html', memories=all_memories)

    @app.route('/about_us')
    def about_us():
        return render_template('about_us.html')

    @app.route('/contact', methods=('GET', 'POST'))
    def contact():
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            subject = request.form['subject']
            message_body = request.form['message']
            error = None

            if not name:
                error = 'Your name is required.'
            elif not email:
                error = 'Your email is required.'
            elif '@' not in email or '.' not in email:
                error = 'Please enter a valid email address.'
            elif not subject:
                error = 'The subject of your message is required.'
            elif not message_body:
                error = 'A message body is required.'

            if error is None:
                email_sent = send_contact_email(name, email, subject, message_body)
                if email_sent:
                    flash('Your message has been sent successfully! We will get back to you soon.', 'success')
                    return redirect(url_for('contact'))
                else:
                    flash('Failed to send your message. Please try again later or contact us directly.', 'error')
            else:
                flash(error, 'warning')

        return render_template('contact.html')

    # --- Admin Portal Routes ---
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        db = get_db()
        total_tours = db.execute("SELECT COUNT(id) FROM tours").fetchone()[0]
        total_users = db.execute("SELECT COUNT(id) FROM users").fetchone()[0]
        total_bookings = db.execute("SELECT COUNT(id) FROM bookings").fetchone()[0]
        paid_bookings = db.execute("SELECT COUNT(id) FROM bookings WHERE payment_status = 'paid'").fetchone()[0]
        pending_bookings = db.execute("SELECT COUNT(id) FROM bookings WHERE payment_status = 'pending'").fetchone()[0]

        return render_template(
            'admin/admin_dashboard.html',
            total_tours=total_tours,
            total_users=total_users,
            total_bookings=total_bookings,
            paid_bookings=paid_bookings,
            pending_bookings=pending_bookings
        )

    @app.route('/admin/tours', methods=('GET', 'POST'))
    @admin_required
    def manage_tours():
        db = get_db()
        if request.method == 'POST':
            action = request.form.get('action')
            tour_id = request.form.get('tour_id', type=int)

            if action == 'add' or action == 'edit':
                name = request.form['name']
                description = request.form['description']
                price = float(request.form['price'])
                date = request.form['date']
                max_participants = int(request.form['max_participants'])
                status = request.form['status']
                error = None

                if not name or not price or not date or not max_participants or not status:
                    error = 'All fields are required.'
                elif price <= 0 or max_participants <= 0:
                    error = 'Price and max participants must be positive.'

                if error is None:
                    try:
                        if action == 'add':
                            db.execute(
                                'INSERT INTO tours (name, description, price, date, max_participants, status, current_participants) VALUES (?, ?, ?, ?, ?, ?, 0)',
                                (name, description, price, date, max_participants, status)
                            )
                            flash('Tour added successfully!', 'success')
                        elif action == 'edit' and tour_id:
                            current_tour_data = db.execute('SELECT current_participants FROM tours WHERE id = ?', (tour_id,)).fetchone()
                            if current_tour_data and current_tour_data['current_participants'] > max_participants:
                                error = f'Max participants ({max_participants}) cannot be less than current participants ({current_tour_data["current_participants"]}).'
                            else:
                                db.execute(
                                    'UPDATE tours SET name = ?, description = ?, price = ?, date = ?, max_participants = ?, status = ? WHERE id = ?',
                                    (name, description, price, date, max_participants, status, tour_id)
                                )
                                flash('Tour updated successfully!', 'success')
                        db.commit()
                        if error is None:
                            return redirect(url_for('manage_tours'))
                    except sqlite3.Error as e:
                        db.rollback()
                        error = f"Database error: {e}"
                flash(error, 'error')

            elif action == 'delete' and tour_id:
                try:
                    db.execute('DELETE FROM tours WHERE id = ?', (tour_id,))
                    db.commit()
                    flash('Tour deleted successfully!', 'success')
                    return redirect(url_for('manage_tours'))
                except sqlite3.Error as e:
                    db.rollback()
                    flash(f'Error deleting tour: {e}', 'error')

        tours_list = db.execute("SELECT * FROM tours ORDER BY date DESC").fetchall()
        return render_template('admin/manage_tours.html', tours=tours_list)

    @app.route('/admin/users')
    @admin_required
    def manage_users():
        db = get_db()
        users_list = db.execute("SELECT id, username, email, is_admin FROM users").fetchall()
        return render_template('admin/manage_users.html', users=users_list)

    @app.route('/admin/users/toggle_admin/<int:user_id>')
    @admin_required
    def toggle_admin_status(user_id):
        db = get_db()
        user = db.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            new_status = 1 if user['is_admin'] == 0 else 0
            db.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_status, user_id))
            db.commit()
            flash(f'User ID {user_id} admin status toggled to {new_status}.', 'success')
        else:
            flash(f'User ID {user_id} not found.', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/users/delete/<int:user_id>')
    @admin_required
    def delete_user(user_id):
        if user_id == g.user['id']:
            flash('You cannot delete your own account while logged in.', 'danger')
            return redirect(url_for('manage_users'))
        db = get_db()
        try:
            db.execute('DELETE FROM users WHERE id = ?', (user_id,))
            db.commit()
            flash(f'User ID {user_id} deleted.', 'success')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Error deleting user: {e}', 'error')
        return redirect(url_for('manage_users'))

    @app.route('/admin/bookings')
    @admin_required
    def view_bookings():
        db = get_db()
        bookings_list = db.execute(
            """
            SELECT
                b.id AS booking_id,
                b.customer_name,
                b.customer_email,
                b.num_participants,
                b.booking_date,
                b.payment_status,
                b.mpesa_receipt,       -- NEW: M-Pesa transaction ID
                b.amount_paid,         -- NEW: Actual amount paid via M-Pesa
                b.phone_number_paid,   -- NEW: Phone number that made the payment
                t.name AS tour_name,
                t.date AS tour_date,
                u.username AS booked_by_username
            FROM bookings b
            JOIN tours t ON b.tour_id = t.id
            LEFT JOIN users u ON b.user_id = u.id
            ORDER BY b.booking_date DESC
            """
        ).fetchall()
        return render_template('admin/view_bookings.html', bookings=bookings_list)

    @app.route('/admin/memories', methods=('GET', 'POST'))
    @admin_required
    def manage_memories():
        db = get_db()
        if request.method == 'POST':
            action = request.form.get('action')
            memory_id = request.form.get('memory_id', type=int)
            title = request.form['title']
            description = request.form['description']
            memory_date = request.form['memory_date']
            tour_id = request.form.get('tour_id', type=int)
            image_file = request.files.get('image_file')

            error = None

            if not title or not memory_date:
                error = 'Title and Memory Date are required.'

            image_filename = request.form.get('existing_image_filename')
            if image_file and image_file.filename:
                new_image_filename = secure_filename(image_file.filename)
                image_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{new_image_filename}"
                image_path = os.path.join(app.root_path, 'static', 'images', image_filename)
                try:
                    image_file.save(image_path)
                    if action == 'edit' and request.form.get('existing_image_filename') and request.form.get('existing_image_filename') != image_filename:
                        old_image_path = os.path.join(app.root_path, 'static', 'images', request.form.get('existing_image_filename'))
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                except Exception as e:
                    error = f"Failed to save image: {e}"

            if action == 'add' and not image_filename:
                error = "Image file is required for adding new memories."

            if error is None:
                try:
                    if action == 'add':
                        db.execute(
                            'INSERT INTO memories (title, description, image_filename, tour_id, memory_date) VALUES (?, ?, ?, ?, ?)',
                            (title, description, image_filename, tour_id if tour_id else None, memory_date)
                        )
                        flash('Memory added successfully!', 'success')
                    elif action == 'edit' and memory_id:
                        db.execute(
                            'UPDATE memories SET title = ?, description = ?, image_filename = ?, tour_id = ?, memory_date = ? WHERE id = ?',
                            (title, description, image_filename, tour_id if tour_id else None, memory_date, memory_id)
                        )
                        flash('Memory updated successfully!', 'success')
                    db.commit()
                    if error is None:
                        return redirect(url_for('manage_memories'))
                except sqlite3.Error as e:
                    db.rollback()
                    error = f"Database error: {e}"
            flash(error, 'error')

        memories_list = db.execute("SELECT m.*, t.name AS tour_name FROM memories m LEFT JOIN tours t ON m.tour_id = t.id ORDER BY memory_date DESC").fetchall()
        tours_list = db.execute("SELECT id, name FROM tours ORDER BY name ASC").fetchall()
        return render_template('admin/edit_memory.html', memories=memories_list, tours=tours_list)

    @app.route('/admin/memories/delete/<int:memory_id>')
    @admin_required
    def delete_memory(memory_id):
        db = get_db()
        try:
            memory = db.execute('SELECT image_filename FROM memories WHERE id = ?', (memory_id,)).fetchone()
            if memory and memory['image_filename']:
                image_path = os.path.join(app.root_path, 'static', 'images', memory['image_filename'])
                if os.path.exists(image_path):
                    os.remove(image_path)
                    flash(f'Associated image {memory["image_filename"]} deleted.', 'info')

            db.execute('DELETE FROM memories WHERE id = ?', (memory_id,))
            db.commit()
            flash('Memory deleted successfully!', 'success')
        except sqlite3.Error as e:
            db.rollback()
            flash(f'Error deleting memory: {e}', 'error')
        return redirect(url_for('manage_memories'))

    return app

from tour_booking_system_v2 import create_app  # or tour_booking_system_v2.factory

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
