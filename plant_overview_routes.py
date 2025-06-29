# Simple routes for plant overview
from flask import render_template, flash, redirect, url_for
from bson import ObjectId
from main import app, login_required, plants_collection, audits_collection, make_serializable

# Note: This should be added to main.py, but due to syntax errors, 
# we'll create a separate file for now

@app.route('/plant/<plant_id>/overview')
@login_required  
def plant_overview(plant_id):
    try:
        plant = plants_collection.find_one({'_id': ObjectId(plant_id)})
        if not plant:
            flash('Plant not found', 'error')
            return redirect(url_for('homepage'))

        # Simple default values for now
        analytics = {
            'power_loss': 25.5,
            'revenue_loss': 45000
        }
        
        progress_data = {
            'pending': 35,
            'resolved': 45,
            'not_found': 20,
            'high': 15,
            'medium': 55,
            'low': 30
        }
        
        plant = make_serializable(plant)
        
        return render_template('plant_overview.html', 
                             plant=plant, 
                             analytics=analytics,
                             progress_data=progress_data)
    except Exception as e:
        print(f"Error in plant_overview: {e}")
        flash('Error loading overview page', 'error')
        return redirect(url_for('homepage'))
