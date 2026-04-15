"""
Gamification Controller
Handles gamification logic, points, badges, achievements, and streaks
"""
from datetime import datetime, date
from app.models import Student, GamificationProfile, LMSActivity
from app.extensions import db


class GamificationController:
    """Controller for managing gamification features"""
    
    # Points configuration
    POINTS = {
        'attendance': 10,
        'attendance_marked': 10,
        'assignment_submit': 20,
        'assignment_submit_early': 30,
        'perfect_grade': 50,
        'grade_improvement': 25,
        'forum_participation': 15,
        'lms_login': 5,
        'prediction_request': 20,
        'counselling_interaction': 20,
        'counselling_attended': 30,
        'challenge_completed': 100,
        'streak_week': 100,
        'streak_month': 500
    }

    ACTION_CATEGORIES = {
        'attendance': 'attendance',
        'attendance_marked': 'attendance',
        'assignment_submit': 'academic',
        'assignment_submit_early': 'academic',
        'perfect_grade': 'academic',
        'grade_improvement': 'improvement',
        'forum_participation': 'engagement',
        'lms_login': 'engagement',
        'prediction_request': 'academic',
        'counselling_interaction': 'engagement',
        'counselling_attended': 'engagement',
        'streak_week': 'attendance',
        'streak_month': 'attendance',
        'challenge_completed': 'improvement',
    }

    SUPPORTED_REALTIME_ACTIONS = set(POINTS.keys())
    
    # Badge definitions
    BADGES = {
        'perfect_attendance_week': {
            'name': 'Perfect Week',
            'description': 'Attended all classes for a week',
            'icon': '🏆'
        },
        'perfect_attendance_month': {
            'name': 'Monthly Champion',
            'description': 'Perfect attendance for a month',
            'icon': '👑'
        },
        'academic_excellence': {
            'name': 'Academic Star',
            'description': 'Maintained an average grade of 18 or above (out of 20)',
            'icon': '⭐'
        },
        'engagement_master': {
            'name': 'Engagement Master',
            'description': 'High engagement score for 3 consecutive weeks',
            'icon': '🎯'
        },
        'improvement_hero': {
            'name': 'Improvement Hero',
            'description': 'Improved grades by more than 20%',
            'icon': '📈'
        },
        'early_bird': {
            'name': 'Early Bird',
            'description': 'Submitted 10 assignments before deadline',
            'icon': '🌅'
        },
        'social_butterfly': {
            'name': 'Social Butterfly',
            'description': 'Active forum participation (50+ posts)',
            'icon': '🦋'
        },
        'comeback_kid': {
            'name': 'Comeback Kid',
            'description': 'Recovered from academic difficulties',
            'icon': '💪'
        }
    }
    
    @staticmethod
    def get_or_create_profile(student_id):
        """Get or create gamification profile for student"""
        profile = GamificationProfile.query.filter_by(student_id=student_id).first()
        
        if not profile:
            profile = GamificationProfile(student_id=student_id)
            db.session.add(profile)
            db.session.commit()
        
        return profile
    
    @staticmethod
    def award_points(student_id, action, custom_points=None):
        """Award points for a specific action"""
        if custom_points is None and action in GamificationController.SUPPORTED_REALTIME_ACTIONS:
            return GamificationController.process_realtime_action(student_id, action)

        profile = GamificationController.get_or_create_profile(student_id)
        
        points = custom_points if custom_points else GamificationController.POINTS.get(action, 0)
        category = GamificationController.ACTION_CATEGORIES.get(action, 'general')
        
        profile.add_points(points, category)
        GamificationController._refresh_ranks_without_commit()
        db.session.commit()
        
        return {
            'points_awarded': points,
            'total_points': profile.total_points,
            'level': profile.level,
            'category': category
        }
    
    @staticmethod
    def update_attendance_streak(student_id, attended=True):
        """Update attendance streak for student"""
        profile = GamificationController.get_or_create_profile(student_id)
        
        if attended:
            profile.update_streak('attendance')
            
            # Award streak badges at thresholds (check both independently, no intermediate commits)
            if profile.current_attendance_streak >= 7:
                week_badge = GamificationController.BADGES.get('perfect_attendance_week')
                if week_badge and not any((b.get('name') == week_badge['name']) for b in (profile.badges or []) if isinstance(b, dict)):
                    profile.award_badge(week_badge['name'], week_badge['description'], week_badge.get('icon'))
                    profile.add_points(GamificationController.POINTS.get('streak_week', 0), 'attendance')
            
            if profile.current_attendance_streak >= 30:
                month_badge = GamificationController.BADGES.get('perfect_attendance_month')
                if month_badge and not any((b.get('name') == month_badge['name']) for b in (profile.badges or []) if isinstance(b, dict)):
                    profile.award_badge(month_badge['name'], month_badge['description'], month_badge.get('icon'))
                    profile.add_points(GamificationController.POINTS.get('streak_month', 0), 'attendance')
        else:
            # Streak broken
            profile.current_attendance_streak = 0
        
        db.session.commit()
        return profile.current_attendance_streak
    
    @staticmethod
    def update_submission_streak(student_id):
        """Update submission streak for student"""
        profile = GamificationController.get_or_create_profile(student_id)
        profile.update_streak('submission')
        db.session.commit()
        return profile.current_submission_streak
    
    @staticmethod
    def award_badge(student_id, badge_key):
        """Award a specific badge to student"""
        profile = GamificationController.get_or_create_profile(student_id)
        badge = GamificationController.BADGES.get(badge_key)
        
        if badge:
            # Check if badge already awarded
            existing_badges = profile.badges or []
            if not any(b.get('name') == badge['name'] for b in existing_badges):
                profile.award_badge(
                    badge_name=badge['name'],
                    badge_description=badge['description'],
                    badge_icon=badge.get('icon')
                )
                db.session.commit()
                return badge
        
        return None
    
    @staticmethod
    def check_and_award_badges(student_id, student_data):
        """Check all badge criteria and award applicable badges"""
        badges_awarded = []
        
        # Academic excellence badge
        if student_data.get('avg_grade', 0) >= 18:
            badge = GamificationController.award_badge(student_id, 'academic_excellence')
            if badge:
                badges_awarded.append(badge)
        
        # Improvement hero badge
        grade_improvement = student_data.get('grade_improvement_percentage', 0)
        if grade_improvement > 20:
            badge = GamificationController.award_badge(student_id, 'improvement_hero')
            if badge:
                badges_awarded.append(badge)
        
        # Early bird badge
        early_submissions = student_data.get('early_submissions', 0)
        if early_submissions >= 10:
            badge = GamificationController.award_badge(student_id, 'early_bird')
            if badge:
                badges_awarded.append(badge)
        
        # Social butterfly badge
        forum_posts = student_data.get('forum_posts', 0)
        if forum_posts >= 50:
            badge = GamificationController.award_badge(student_id, 'social_butterfly')
            if badge:
                badges_awarded.append(badge)
        
        return badges_awarded
    
    @staticmethod
    def unlock_achievement(student_id, achievement_name, achievement_description):
        """Unlock a custom achievement"""
        profile = GamificationController.get_or_create_profile(student_id)
        
        # Check if achievement already unlocked
        existing_achievements = profile.achievements or []
        if not any(a.get('name') == achievement_name for a in existing_achievements):
            profile.unlock_achievement(achievement_name, achievement_description)
            db.session.commit()
            return True
        
        return False
    
    @staticmethod
    def get_leaderboard(scope='school', limit=10):
        """Get leaderboard rankings"""
        query = GamificationProfile.query.order_by(GamificationProfile.total_points.desc())
        
        if scope == 'class':
            # Would need class information to filter
            pass
        
        profiles = query.limit(limit).all()
        
        leaderboard = []
        for rank, profile in enumerate(profiles, 1):
            student = Student.query.get(profile.student_id)
            leaderboard.append({
                'rank': rank,
                'student_id': profile.student_id,
                'student_name': student.name if student else 'Unknown',
                'total_points': profile.total_points,
                'level': profile.level,
                'badges_count': len(profile.badges or []),
                'achievements_count': len(profile.achievements or [])
            })
        
        return leaderboard
    
    @staticmethod
    def update_leaderboard_ranks():
        """Update leaderboard ranks for all profiles"""
        # Get all profiles ordered by points
        profiles = GamificationProfile.query.order_by(GamificationProfile.total_points.desc()).all()
        
        for rank, profile in enumerate(profiles, 1):
            profile.rank_in_school = rank
            # rank_in_class would require class information
        
        db.session.commit()

    @staticmethod
    def _refresh_ranks_without_commit():
        """Refresh in-memory leaderboard ranks for all profiles."""
        profiles = GamificationProfile.query.order_by(GamificationProfile.total_points.desc()).all()
        for rank, ranked_profile in enumerate(profiles, 1):
            ranked_profile.rank_in_school = rank

    @staticmethod
    def _get_or_create_today_lms_activity(student_id):
        """Get or create today's LMS activity record for counter-based actions."""
        today = datetime.utcnow().date()
        activity = (
            LMSActivity.query
            .filter_by(student_id=student_id)
            .order_by(LMSActivity.activity_date.desc())
            .first()
        )

        if activity and activity.activity_date and activity.activity_date.date() == today:
            return activity

        activity = LMSActivity(student_id=student_id, activity_date=datetime.utcnow())
        db.session.add(activity)
        return activity

    @staticmethod
    def _calculate_badge_context(student_id, extra_context=None):
        """Build badge context from student and latest LMS data."""
        student = Student.query.get(student_id)
        latest_lms = (
            LMSActivity.query
            .filter_by(student_id=student_id)
            .order_by(LMSActivity.activity_date.desc())
            .first()
        )

        sem1_grade = student.curricular_units_1st_sem_grade if student else 0
        sem2_grade = student.curricular_units_2nd_sem_grade if student else 0
        avg_grade = ((sem1_grade + sem2_grade) / 2) if student else 0

        grade_improvement_percentage = 0
        if sem1_grade > 0 and sem2_grade > sem1_grade:
            grade_improvement_percentage = ((sem2_grade - sem1_grade) / sem1_grade) * 100

        context = {
            'avg_grade': avg_grade,
            'grade_improvement_percentage': grade_improvement_percentage,
            'early_submissions': latest_lms.assignment_submissions if latest_lms else 0,
            'forum_posts': latest_lms.forum_posts if latest_lms else 0,
        }

        if extra_context:
            context.update(extra_context)

        return context

    @staticmethod
    def _award_badges_without_commit(profile, student_data):
        """Evaluate and append newly earned badges in-memory without committing."""
        awarded_badges = []

        checks = [
            ('academic_excellence', student_data.get('avg_grade', 0) >= 18),
            ('improvement_hero', student_data.get('grade_improvement_percentage', 0) > 20),
            ('early_bird', student_data.get('early_submissions', 0) >= 10),
            ('social_butterfly', student_data.get('forum_posts', 0) >= 50),
        ]

        existing_badges = profile.badges or []
        existing_names = {b.get('name') for b in existing_badges if isinstance(b, dict)}

        for badge_key, condition in checks:
            if not condition:
                continue
            badge = GamificationController.BADGES.get(badge_key)
            if not badge or badge['name'] in existing_names:
                continue
            profile.award_badge(
                badge_name=badge['name'],
                badge_description=badge['description'],
                badge_icon=badge.get('icon')
            )
            existing_names.add(badge['name'])
            awarded_badges.append(badge['name'])

        return awarded_badges

    @staticmethod
    def process_realtime_action(student_id, action, attended=True, badge_context=None):
        """Award points/streaks/badges for a user action and refresh ranks immediately."""
        if action == 'attendance':
            action = 'attendance_marked'

        if action not in GamificationController.SUPPORTED_REALTIME_ACTIONS:
            raise ValueError(f'Unsupported gamification action: {action}')

        profile = GamificationController.get_or_create_profile(student_id)
        points_awarded = 0
        category = GamificationController.ACTION_CATEGORIES.get(action, 'general')

        if action in {'attendance_marked'}:
            if attended:
                points_awarded = GamificationController.POINTS.get('attendance_marked', 0)
                profile.add_points(points_awarded, 'attendance')
                profile.update_streak('attendance')

                if profile.current_attendance_streak >= 7:
                    week_badge = GamificationController.BADGES.get('perfect_attendance_week')
                    if week_badge:
                        if not any((b.get('name') == week_badge['name']) for b in (profile.badges or []) if isinstance(b, dict)):
                            profile.award_badge(week_badge['name'], week_badge['description'], week_badge.get('icon'))
                            profile.add_points(GamificationController.POINTS.get('streak_week', 0), 'attendance')

                if profile.current_attendance_streak >= 30:
                    month_badge = GamificationController.BADGES.get('perfect_attendance_month')
                    if month_badge:
                        if not any((b.get('name') == month_badge['name']) for b in (profile.badges or []) if isinstance(b, dict)):
                            profile.award_badge(month_badge['name'], month_badge['description'], month_badge.get('icon'))
                            profile.add_points(GamificationController.POINTS.get('streak_month', 0), 'attendance')
            else:
                profile.current_attendance_streak = 0
                profile.last_activity_date = datetime.utcnow().date()
        else:
            points_awarded = GamificationController.POINTS.get(action, 0)
            if points_awarded:
                profile.add_points(points_awarded, category)

            if action in {'assignment_submit', 'assignment_submit_early'}:
                profile.update_streak('submission')
                lms_activity = GamificationController._get_or_create_today_lms_activity(student_id)
                lms_activity.assignment_submissions = (lms_activity.assignment_submissions or 0) + 1

            if action == 'forum_participation':
                lms_activity = GamificationController._get_or_create_today_lms_activity(student_id)
                lms_activity.forum_posts = (lms_activity.forum_posts or 0) + 1

            if action == 'lms_login':
                lms_activity = GamificationController._get_or_create_today_lms_activity(student_id)
                lms_activity.login_count = (lms_activity.login_count or 0) + 1

            if action == 'challenge_completed':
                profile.challenges_completed = (profile.challenges_completed or 0) + 1

        student_data = GamificationController._calculate_badge_context(student_id, badge_context)
        new_badges = GamificationController._award_badges_without_commit(profile, student_data)

        GamificationController._refresh_ranks_without_commit()

        db.session.commit()

        return {
            'student_id': student_id,
            'action': action,
            'points_awarded': points_awarded,
            'total_points': profile.total_points,
            'level': profile.level,
            'current_streak': profile.current_streak,
            'new_badges': new_badges,
            'rank_in_school': profile.rank_in_school,
        }
    
    @staticmethod
    def get_student_progress(student_id):
        """Get comprehensive progress information for student"""
        profile = GamificationController.get_or_create_profile(student_id)
        student = Student.query.get(student_id)
        
        # Calculate progress to next level
        points_needed = profile.experience_to_next_level - profile.total_points
        progress_percentage = (profile.total_points / profile.experience_to_next_level) * 100
        
        return {
            'student_name': student.name if student else 'Unknown',
            'level': profile.level,
            'total_points': profile.total_points,
            'points_to_next_level': points_needed,
            'progress_percentage': progress_percentage,
            'points_breakdown': {
                'academic': profile.academic_points,
                'attendance': profile.attendance_points,
                'engagement': profile.engagement_points,
                'improvement': profile.improvement_points
            },
            'streaks': {
                'current_attendance': profile.current_attendance_streak,
                'longest_attendance': profile.longest_attendance_streak,
                'current_submission': profile.current_submission_streak,
                'longest_submission': profile.longest_submission_streak
            },
            'badges': profile.badges or [],
            'achievements': profile.achievements or [],
            'challenges_completed': profile.challenges_completed,
            'current_challenges': profile.current_challenges or [],
            'rank_in_school': profile.rank_in_school
        }
    
    @staticmethod
    def assign_challenge(student_id, challenge_name, challenge_description, target_value):
        """Assign a new challenge to student"""
        profile = GamificationController.get_or_create_profile(student_id)
        
        challenge = {
            'name': challenge_name,
            'description': challenge_description,
            'target_value': target_value,
            'current_progress': 0,
            'assigned_at': datetime.utcnow().isoformat(),
            'status': 'active'
        }
        
        if profile.current_challenges is None:
            profile.current_challenges = []
        
        profile.current_challenges.append(challenge)
        db.session.commit()
        
        return challenge
    
    @staticmethod
    def update_challenge_progress(student_id, challenge_name, progress_value):
        """Update progress on a specific challenge"""
        profile = GamificationController.get_or_create_profile(student_id)
        
        if profile.current_challenges:
            for challenge in profile.current_challenges:
                if challenge.get('name') == challenge_name and challenge.get('status') == 'active':
                    challenge['current_progress'] = progress_value
                    
                    # Check if challenge completed
                    if progress_value >= challenge.get('target_value', 0):
                        challenge['status'] = 'completed'
                        challenge['completed_at'] = datetime.utcnow().isoformat()
                        
                        # Award points for completing challenge
                        GamificationController.process_realtime_action(student_id, 'challenge_completed')
                    
                    db.session.commit()
                    return challenge
        
        return None
    
    @staticmethod
    def initialize_profile(student_id):
        """Initialize gamification profile for a student"""
        return GamificationController.get_or_create_profile(student_id)
    
    @staticmethod
    def get_student_rank(student_id):
        """Get student's rank in leaderboard"""
        profile = GamificationProfile.query.filter_by(student_id=student_id).first()
        if not profile:
            return None
        
        # Count profiles with higher points
        rank = GamificationProfile.query.filter(
            GamificationProfile.total_points > profile.total_points
        ).count() + 1
        
        return rank
    
    @staticmethod
    def get_achievement_timeline(student_id):
        """Get achievement timeline for a student"""
        profile = GamificationProfile.query.filter_by(student_id=student_id).first()
        if not profile:
            return []
        
        timeline = []
        
        # Add badge achievements
        if profile.badges_earned:
            for badge in profile.badges_earned:
                timeline.append({
                    'type': 'badge',
                    'title': badge,
                    'description': f'Earned {badge} badge',
                    'date': 'Recently'  # Would need badge timestamp
                })
        
        # Add level milestones
        current_level = profile.level
        for level in range(1, current_level + 1):
            if level % 5 == 0:  # Milestone levels
                timeline.append({
                    'type': 'level',
                    'title': f'Reached Level {level}',
                    'description': f'Leveled up to {level}',
                    'date': 'Past'
                })
        
        return timeline[-10:]  # Return last 10 events
    
    @staticmethod
    def calculate_level_progress(total_points):
        """Calculate level progress information"""
        # Simple level calculation: 1000 points per level
        points_per_level = 1000
        current_level = (total_points // points_per_level) + 1
        points_in_current_level = total_points % points_per_level
        points_needed_for_next = points_per_level
        percentage = int((points_in_current_level / points_needed_for_next) * 100)
        
        return {
            'current_level': current_level,
            'next_level': current_level + 1,
            'current_points': points_in_current_level,
            'points_needed': points_needed_for_next,
            'points_to_next': points_needed_for_next - points_in_current_level,
            'percentage': percentage
        }
    
    @staticmethod
    def get_leaderboard_statistics():
        """Get overall leaderboard statistics"""
        total_students = GamificationProfile.query.count()
        total_points = db.session.query(db.func.sum(GamificationProfile.total_points)).scalar() or 0
        
        # Count total badges
        total_badges = 0
        profiles = GamificationProfile.query.all()
        for profile in profiles:
            if profile.badges_earned:
                total_badges += len(profile.badges_earned)
        
        # Get highest streak from both attendance and submission streaks
        max_attendance = db.session.query(db.func.max(GamificationProfile.current_attendance_streak)).scalar() or 0
        max_submission = db.session.query(db.func.max(GamificationProfile.current_submission_streak)).scalar() or 0
        highest_streak = max(max_attendance, max_submission)
        
        return {
            'total_students': total_students,
            'total_points': total_points,
            'total_badges': total_badges,
            'highest_streak': highest_streak,
            'avg_points': int(total_points / total_students) if total_students > 0 else 0
        }
    
    @staticmethod
    def get_all_available_badges():
        """Get all available badges with metadata"""
        badges = {
            'High Achiever': {
                'icon': 'fa-trophy',
                'color': '#FFD700',
                'description': 'Consistently high academic performance',
                'requirement': 'Maintain average grade >= 18/20',
                'points': 500
            },
            'Perfect Attendance': {
                'icon': 'fa-calendar-check',
                'color': '#28a745',
                'description': 'Never missed a class',
                'requirement': 'Zero absences for the semester',
                'points': 300
            },
            'Early Bird': {
                'icon': 'fa-sun',
                'color': '#FFA500',
                'description': 'Always submits assignments early',
                'requirement': 'Submit 10 assignments before deadline',
                'points': 200
            },
            'Engagement Master': {
                'icon': 'fa-comments',
                'color': '#007bff',
                'description': 'Highly engaged in class activities',
                'requirement': 'High engagement score for 3 weeks',
                'points': 400
            },
            'Improvement Champion': {
                'icon': 'fa-chart-line',
                'color': '#17a2b8',
                'description': 'Significant academic improvement',
                'requirement': 'Improve grades by 20% or more',
                'points': 350
            },
            'Social Butterfly': {
                'icon': 'fa-user-friends',
                'color': '#e83e8c',
                'description': 'Active in peer interactions',
                'requirement': 'High peer interaction level',
                'points': 250
            },
            'Streak Master': {
                'icon': 'fa-fire',
                'color': '#dc3545',
                'description': 'Maintained longest streak',
                'requirement': '30-day activity streak',
                'points': 600
            },
            'Comeback Kid': {
                'icon': 'fa-heart',
                'color': '#6610f2',
                'description': 'Recovered from difficulties',
                'requirement': 'Improve from at-risk status',
                'points': 450
            }
        }
        return badges
