from flask import Flask, jsonify, render_template
import json

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/clubs')
def get_clubs():
    with open('clubs.json', encoding='utf-8') as f:
        data = json.load(f)
    # Filter clubs with lat_lng
    clubs_with_latlng = [club for club in data.values() if club['lat_lng'] is not None]
    return jsonify(clubs_with_latlng)

if __name__ == '__main__':
    app.run(debug=True)