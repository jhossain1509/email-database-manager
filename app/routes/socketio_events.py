"""
SocketIO event handlers for real-time job monitoring
"""
from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room
from app import socketio


@socketio.on('connect', namespace='/jobs')
def handle_connect():
    """Handle client connection"""
    if current_user.is_authenticated:
        print(f'Client connected: {current_user.username}')
        emit('connection_response', {'status': 'connected', 'user': current_user.username})
    else:
        print('Unauthenticated client attempted to connect')
        return False


@socketio.on('disconnect', namespace='/jobs')
def handle_disconnect():
    """Handle client disconnection"""
    if current_user.is_authenticated:
        print(f'Client disconnected: {current_user.username}')


@socketio.on('join_job', namespace='/jobs')
def handle_join_job(data):
    """Join a specific job room for targeted updates"""
    if current_user.is_authenticated:
        job_id = data.get('job_id')
        if job_id:
            join_room(job_id)
            print(f'User {current_user.username} joined job room: {job_id}')
            emit('join_response', {'status': 'joined', 'job_id': job_id})


@socketio.on('leave_job', namespace='/jobs')
def handle_leave_job(data):
    """Leave a specific job room"""
    if current_user.is_authenticated:
        job_id = data.get('job_id')
        if job_id:
            leave_room(job_id)
            print(f'User {current_user.username} left job room: {job_id}')
            emit('leave_response', {'status': 'left', 'job_id': job_id})
