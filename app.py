import os 
import sqlite3
from flask import Flask, render_template, session, request, redirect, g, current_app, json, flash
from flask_session import Session
import sqlalchemy as db
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date, datetime, timedelta

import base64
from io import BytesIO
from matplotlib.figure import Figure
import numpy as np

from helpers import login_required, apology
from cal import cal_create, cal_update, cal_delete
from cal_auth import cal_auth

app = Flask(__name__, static_folder=os.path.abspath('/Users/Bonnielu/Documents/Personal Projects/Code/Period./templates/assets'))

# Ensures templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Create database connection
engine = db.create_engine('sqlite:////Users/Bonnielu/Documents/Personal Projects/Code/Period./period.db')
metadata = db.MetaData()

@app.route('/', methods=["GET", "POST"])
@login_required
def main():

    if request.method == "POST":
        # Get user input and convert string to datetime
        start = request.form.get("start")
        start = datetime.strptime(start, "%Y-%m-%d")

        end = request.form.get("end")
        end = datetime.strptime(end, "%Y-%m-%d")

        # Calculate length of period
        delta = end - start
        length = delta.days
        if int(length) < 0:
            flash('End date must occur after start date', 'danger')
            return render_template("fullcalendar.html")
        
        with engine.begin() as connection:
            history = db.Table('history', metadata, autoload=True, autoload_with=engine)
            users = db.Table('users', metadata, autoload=True, autoload_with=engine)
            # Fetch most recent end date.
            query = db.select([history.columns.end_date, history.columns.start_date]).where(history.columns.user_id == session["user_id"]).order_by(db.desc(history.columns.start_date))

            ResultProxy = connection.execute(query)
            ResultSet = ResultProxy.fetchall()

            # If no history, interval cannot be calculated 
            if not ResultSet:
                interval = None
            else:
                # Calculate interval between this period start-date and last period end-date
                for i in range(len(ResultSet)):
                    prev_end = ResultSet[i]["end_date"]
                    prev_end = datetime.strptime(prev_end, "%Y-%m-%d %H:%M:%S")
                    interval = (start - prev_end).days

                    # Accounts for user inputting less recent value
                    if interval > 0:
                        break
                    elif i == len(ResultSet) - 1:
                        # Update interval of what was previously the first date.
                        prev_start = ResultSet[i]["start_date"]
                        prev_start = datetime.strptime(prev_start, "%Y-%m-%d %H:%M:%S")

                        interval = (prev_start - end).days

                        query = db.update(history).values(interval=interval).where(db.and_(history.columns.interval==None, history.columns.user_id==session["user_id"]))
                        ResultProxy = connection.execute(query)

                        interval = None
                        prev_end = None
                        
                        
            # Insert start, end, length, interval into history table 
            query = db.insert(history).values(user_id=session["user_id"], 
                start_date=start, end_date=end, length=length, interval=interval)
            ResultProxy = connection.execute(query)

            # Calculate current average of length and interval
            query = db.select([db.func.sum(history.columns.length), db.func.count(history.columns.length),
                db.func.sum(history.columns.interval), db.func.count(history.columns.interval)]).where(history.columns.user_id == session["user_id"])
            ResultProxy = connection.execute(query)
            ResultSet = ResultProxy.fetchone()

            avg_length = float("{:.1f}".format(float(ResultSet[0]) / float(ResultSet[1])))

            if not ResultSet[2]:
                avg_interval = 28
            else:
                avg_interval = "{:.1f}".format(float(ResultSet[2]) / float(ResultSet[3]))

            # Get most recent end date
            query = db.select([history.columns.end_date]).where(history.columns.user_id == session["user_id"]).order_by(db.desc(history.columns.end_date))
            ResultProxy = connection.execute(query)
            prev_end = ResultProxy.fetchone()[0]
            prev_end = datetime.strptime(prev_end, '%Y-%m-%d %H:%M:%S')

            # Update db with new start date, interval, and length of repeating event
            if prev_end:
                start = date(prev_end.year, prev_end.month, prev_end.day)+timedelta(days=round(float(avg_interval)))
                start = start.isoformat()
            else:
                start = start.isoformat()
            query = db.update(users).values(avg_length=avg_length, avg_interval=avg_interval, start=start).where(users.columns.id == session["user_id"])
            ResultProxy = connection.execute(query)

            # Query users table for event id 
            query = db.select([users.columns.event_id]).where(users.columns.id == session["user_id"])
            ResultProxy = connection.execute(query)
            event_id = ResultProxy.fetchone() 

            # If event_id not previously recorded, create new event in google calendar
            if not event_id[0]:
                event_result = cal_create(avg_length, avg_interval, end)
                event_id = event_result["id"]
                query = db.update(users).values(event_id=event_id).where(users.columns.id == session["user_id"])
                ResultProxy = connection.execute(query)
                repeat_event = event_result["start"]["date"][0:10]

            # If recorded, update event in google calendar
            else:
                repeat_event = cal_update(avg_length, avg_interval, prev_end, event_id[0])
                repeat_event = repeat_event["start"]["date"][0:10]

            # Get previous periods
            query = db.select([history.columns.start_date, history.columns.end_date]).where(history.columns.user_id == session["user_id"])
            ResultProxy = connection.execute(query)
            prev_events = ResultProxy.fetchall()

            query = db.select([db.func.count(history.columns.length)]).where(history.columns.user_id == session["user_id"])
            ResultProxy = connection.execute(query)
            count = ResultProxy.fetchone()
        
        prev_events = [list(ele) for ele in prev_events] 
        
        flash('Period Logged!', 'success')

        return render_template("fullcalendar.html", avg_interval=avg_interval, avg_length=avg_length,
            prev_events=prev_events, count=count[0], startDay=repeat_event)
    else:
        with engine.begin() as connection:
            users = db.Table('users', metadata, autoload=True, autoload_with=engine)
            history = db.Table('history', metadata, autoload=True, autoload_with=engine)
            query = db.select([users.columns.avg_interval, users.columns.avg_length, users.columns.start]).where(users.columns.id == session["user_id"])
            ResultProxy = connection.execute(query)
            event_result = ResultProxy.fetchall()

            query = db.select([history.columns.start_date, history.columns.end_date]).where(history.columns.user_id == session["user_id"]).order_by(db.desc(history.columns.start_date))
            ResultProxy = connection.execute(query)
            prev_events = ResultProxy.fetchall()

            query = db.select([db.func.count(history.columns.length)]).where(history.columns.user_id == session["user_id"])
            ResultProxy = connection.execute(query)
            count = ResultProxy.fetchone()
        
            prev_events = [list(ele) for ele in prev_events]

        if not prev_events:
            return render_template("fullcalendar.html", count=0, avg_interval=json.dumps(None), startDay=json.dumps(None), avg_length=json.dumps(None), prev_events=json.dumps(None))

        return render_template("fullcalendar.html", avg_length=event_result[0][1],
            avg_interval=event_result[0][0], startDay=event_result[0][2][0:10], prev_events=prev_events, count=count[0])


@app.route('/reports') 
@login_required
def reports():
    with engine.begin() as connection:
        history = db.Table('history', metadata, autoload=True, autoload_with=engine)
        
        # Select query from history table
        query = db.select([history]).where(history.columns.user_id == session["user_id"]).order_by(db.asc(history.columns.start_date))
        ResultProxy = connection.execute(query)
        ResultSet = ResultProxy.fetchall()

        # Append data for date vs interval plot
        data_interval = []
        dates = []

        data_length = []
        date_length = []

        for row in ResultSet:
            if row[4]:
                data_interval.append(int(row[4]))
                dates.append(datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").date())
            
            if row[3]:
                data_length.append(int(row[3]))
                date_length.append(datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").date())

        
    # Generate the figure without using pyplot

    fig = Figure(figsize=(11, 6))
    ax = fig.subplots()
    ax.scatter(x=dates, y=data_interval, c='r')
    ax.plot(dates, data_interval, ":", c='r')
    ax.set_title("Cycle Length History", pad=15)
    ax.set_xlabel("Start Date")
    ax.set_ylabel("Cycle Length (Days)")
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    # Save to a temporary buffer
    buf = BytesIO()
    fig.savefig(buf, format="png")

    # Embed result in html output
    data = base64.b64encode(buf.getbuffer()).decode("ascii")

    # Repeat process but for different graph

    fig = Figure(figsize=(11, 6))
    ax = fig.subplots()
    ax.scatter(x=date_length, y=data_length, c='r')
    ax.plot(date_length, data_length, ":", c='r')
    ax.set_title("Period Length History", pad=15)
    ax.set_xlabel("Start Date")
    ax.set_ylabel("Period Length (Days)")
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    # Save to a temporary buffer
    buf = BytesIO()
    fig.savefig(buf, format="png")

    # Embed result in html output
    data2 = base64.b64encode(buf.getbuffer()).decode("ascii")

    if not data_interval or not data_length:
        flash("Statistics Incomplete. Please log more periods!", "danger")
    return render_template("reports.html", interval_img=f"data:image/png;base64,{data}", length_img=f"data:image/png;base64,{data2}")


@app.route('/login', methods=["GET","POST"])
def login():
    """User Login"""

    # Forgets any user_id
    session.clear()

    if request.method == "POST":
        # Query database for username
        with engine.begin() as connection:
            users = db.Table('users', metadata, autoload=True, autoload_with=engine)
            query = db.select([users]).where(users.columns.username == request.form.get("username"))

            # Ensure that username exists and password is correct
            ResultProxy = connection.execute(query)
            ResultSet = ResultProxy.fetchall()

            if len(ResultSet) != 1 or not check_password_hash(ResultSet[0]["password"], request.form.get("password")):
                flash("Incorrect Username or Password!", "danger")
                return render_template("login.html")

            # Remember which user has logged in
            session["user_id"] = ResultSet[0]["id"]

            # Redirect user to homepage
            return redirect('/')
    else:
        return render_template('login.html')

@app.route('/register', methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure passwords match
        if request.form.get("password") != request.form.get("password_again"):
            flash("Passwords must match", "danger")
            return render_template("register.html")
            
        # Ensure unique username and email
        with engine.connect() as connection:
            users = db.Table('users', metadata, autoload=True, autoload_with=engine)
            query = db.select([users.columns.username,users.columns.email])
            ResultProxy = connection.execute(query)
            ResultSet = ResultProxy.fetchall()

            for user in ResultSet:
                if user["username"] == request.form.get("username"):
                    flash("Username already taken. Please choose different one.", "danger")
                    return render_template("register.html")
                elif user["email"] == request.form.get("email"):
                    flash("Email already in use. Already have an account?", "danger")
                    return render_template("register.html")

            # Insert information into database
            query = db.insert(users).values(username=request.form.get("username"), 
                password=generate_password_hash(request.form.get("password")), email=request.form.get("email"))
            ResultProxy = connection.execute(query)

        flash("Registered!", "success")
        
        return redirect('/')
    else:
        return render_template("register.html")

@app.route('/logout')
def logout():
    session.clear()

    # Redirect user to login form
    return redirect('/login')


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
