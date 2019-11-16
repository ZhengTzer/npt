from scripts import tabledef
from scripts import forms
from scripts import helpers
from flask import Flask, redirect, url_for, render_template, request, session, send_file, make_response
from werkzeug.utils import secure_filename
from io import StringIO
from io import BytesIO
import io
from flask_jsonpify import jsonpify

import ast
import csv
import ast
import json
import sys
import os
import stripe
import pandas as pd
import numpy as np
from numpy import array


import time
from datetime import datetime, timedelta
from dateutil.relativedelta import *
import matplotlib.pyplot as plt

from lifetimes.plotting import *
from lifetimes.utils import *
from lifetimes import BetaGeoFitter
from lifetimes.plotting import plot_frequency_recency_matrix
from lifetimes.plotting import plot_probability_alive_matrix
from lifetimes.plotting import plot_period_transactions
from lifetimes.plotting import plot_history_alive
from lifetimes import GammaGammaFitter
from lifetimes.plotting import plot_calibration_purchases_vs_holdout_purchases
from lifetimes.utils import calibration_and_holdout_data

app = Flask(__name__)

# app.secret_key = os.urandom(12)  # Generic key for dev purposes only
app.secret_key = b'\xd9e\x0cm5\xf4\x7f@\xfb\xee[\xa1'


stripe_keys = {
  'secret_key':'sk_test_gIz6GEr5lWI18DfYySMEhJDc00J6cpbSaV', #os.environ['secret_key'],
  'publishable_key':'pk_test_GfV4kl0nfS6Eb8Wr0sBOPMss009QCCHLpN' #os.environ['publishable_key']
}

stripe.api_key = stripe_keys['secret_key']

# Heroku
#from flask_heroku import Heroku
#heroku = Heroku(app)

# ======== Routing =========================================================== #
# -------- Login ------------------------------------------------------------- #
@app.route('/', methods=['GET', 'POST'])
def login():
    if not session.get('logged_in'):
        form = forms.LoginForm(request.form)
        if request.method == 'POST':
            username = request.form['username'].lower()
            password = request.form['password']
            if form.validate():
                if helpers.credentials_valid(username, password):
                    session['logged_in'] = True
                    session['username'] = username
                    return json.dumps({'status': 'Login successful'})
                return json.dumps({'status': 'Invalid user/pass'})
            return json.dumps({'status': 'Both fields required'})
        return render_template('login.html', form=form)
    user = helpers.get_user()
    user.active = user.payment == helpers.payment_token()
    user.key = stripe_keys['publishable_key']
    return render_template('home.html', user=user)

# -------- Signup ---------------------------------------------------------- #
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if not session.get('logged_in'):
        form = forms.LoginForm(request.form)
        if request.method == 'POST':
            username = request.form['username'].lower()
            password = helpers.hash_password(request.form['password'])
            email = request.form['email']
            if form.validate():
                if not helpers.username_taken(username):
                    helpers.add_user(username, password, email)
                    session['logged_in'] = True
                    session['username'] = username
                    return json.dumps({'status': 'Signup successful'})
                return json.dumps({'status': 'Username taken'})
            return json.dumps({'status': 'User/Pass required'})
        return render_template('login.html', form=form)
    return redirect(url_for('login'))


# -------- Settings ---------------------------------------------------------- #
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if session.get('logged_in'):
        if request.method == 'POST':
            password = request.form['password']
            if password != "":
                password = helpers.hash_password(password)
            email = request.form['email']
            helpers.change_user(password=password, email=email)
            return json.dumps({'status': 'Saved'})
        user = helpers.get_user()
        return render_template('settings.html', user=user)
    return redirect(url_for('login'))

# -------- Charge ---------------------------------------------------------- #
@app.route('/charge', methods=['POST'])
def charge():
    if session.get('logged_in'):
        user = helpers.get_user()
        try:
            amount = 1000   # amount in cents
            customer = stripe.Customer.create(
                email= user.email,
                source=request.form['stripeToken']
            )
            stripe.Charge.create(
                customer=customer.id,
                amount=amount,
                currency='usd',
                description='Resume Scanner Donation'
            )
            helpers.change_user(payment=helpers.payment_token())
            user.active = True
            return render_template('home.html', user=user)
        except stripe.error.StripeError:
            return render_template('error.html')

@app.route("/logout")
def logout():
    session['logged_in'] = False
    return redirect(url_for('login'))

@app.route('/predict', methods=['GET', 'POST'])
def upload():
    # -*- coding: utf-8 -*-
    if request.method == 'POST':
        f = request.files['file']

        basepath = os.path.dirname(__file__)
        file_path = os.path.join(
            basepath, 'uploads', secure_filename(f.filename))
        f.save(file_path)
        df = pd.read_csv(file_path)

        df['salesDate'] = pd.to_datetime(df['salesDate'])

        cols_of_interest = ['memberID', 'salesDate', 'sales']
        df = df[cols_of_interest]

        max_date = df['salesDate'].max()
        min_date = max_date - relativedelta(months=+12)

        df = df.loc[(df['salesDate'] >= min_date) & (df['salesDate'] <= max_date)]

        min_order = df['salesDate'].min()
        max_order = df['salesDate'].max()
        data = summary_data_from_transaction_data(df, 'memberID', 'salesDate', monetary_value_col='sales', observation_period_end=max_order)
        
        d2 = data.sort_values('frequency', ascending=False)

        bgf = BetaGeoFitter(penalizer_coef=0.001)
        bgf.fit(data['frequency'], data['recency'], data['T'])

        t = 14
        data['predicted_purchases'] = bgf.conditional_expected_number_of_purchases_up_to_time(t, data['frequency'], data['recency'], data['T'])
        data.sort_values(by='predicted_purchases', ascending=False, inplace=True)
        data2 = data.head(3)
        
        return data2.to_html()
        #return render_template('downloads.html', tables=[data2.to_html(classes="data")], header="true")
    return None


# ======== Main ============================================================== #
if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)