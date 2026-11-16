# File: src/core/progress_integration.py
"""
BUGFIX: Bridge between Mastery Tracking and User Progress Systems
Fixed the specific errors found in debug logs
"""

import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

class ProgressIntegrationBridge:
    """
    FIXED: Connects mastery tracking results to user progress updates
    Ensures that learning achievements translate to visible progress
    """
    
    def __init__(self, redis_client, mastery_tracker):
        self.redis_client = redis_client
        self.mastery_tracker = mastery_tracker
        
        # Progress thresholds
        self.GO_COMPLETION_THRESHOLD = 0.8  # 80% mastery = GO completed
        self.WEEK_COMPLETION_THRESHOLD = 0.75  # 75% of GOs completed = week completed
        self.LO_COMPLETION_THRESHOLD = 0.8   # 80% mastery = LO completed
        
        print("DEBUG: ProgressIntegrationBridge initialized")
    
    def update_progress_from_mastery(self, username: str, course: str, week: int, 
                                   interaction_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        FIXED: Update user progress based on latest mastery achievements
        Call this after every mastery update (quiz/tutor)
        """
        try:
            print(f"DEBUG: 🔄 FIXED: Updating progress from mastery for {username} in {course} W{week}")
            
            # FORCE fresh mastery data load (bypass any caching)
            mastery_summary = self._get_fresh_mastery_data_fixed(username, course)
            print(f"DEBUG: 📊 Fresh mastery data - GO count: {len(mastery_summary.get('go_masteries', {}))}")
            
            # Calculate progress updates with ENHANCED logic
            progress_updates = self._calculate_progress_from_mastery_enhanced_fixed(
                mastery_summary, week, interaction_context
            )
            
            print(f"DEBUG: 🔢 Progress calculation result: {progress_updates}")
            
            # Apply progress updates to Redis with ENHANCED error checking
            updated_progress = self._apply_progress_updates_enhanced(
                username, course, week, progress_updates
            )
            
            # Check for week advancement
            week_advancement = self._check_week_advancement(
                username, course, week, mastery_summary
            )
            
            result = {
                "progress_updated": updated_progress is not None,
                "completion_change": progress_updates.get("completion_increment", 0.0),
                "week_advanced": week_advancement.get("advanced", False),
                "next_week": week_advancement.get("next_week"),
                "achievements": progress_updates.get("achievements", []),
                "mastery_triggered": True,
                "debug_info": {
                    "mastery_go_count": len(mastery_summary.get("go_masteries", {})),
                    "week_gos_found": progress_updates.get("total_gos", 0),
                    "completed_gos": progress_updates.get("completed_gos", 0),
                    "calculation_method": progress_updates.get("calculation_method", "unknown")
                }
            }
            
            print(f"DEBUG: ✅ FIXED Progress integration result: {result}")
            return result
            
        except Exception as e:
            print(f"ERROR: FIXED Progress integration failed: {e}")
            import traceback
            traceback.print_exc()
            return {"progress_updated": False, "error": str(e)}
    
    def _get_fresh_mastery_data_fixed(self, username: str, course: str) -> Dict[str, Any]:
        """FIXED: Force fresh mastery data load with proper data format handling"""
        try:
            print(f"DEBUG: 🔄 Getting fresh mastery data for {username}:{course}")
            
            # Method 1: Direct Redis access with latest key
            latest_key = f"mastery:{username}:{course}:latest"
            fresh_data = self.redis_client.get_redis().get(latest_key)
            if fresh_data:
                print(f"DEBUG: 🔥 Got latest mastery data from Redis")
                raw_data = json.loads(fresh_data)
                return self._format_mastery_data_fixed(raw_data)
            
            # Method 2: Regular mastery tracker
            if hasattr(self.mastery_tracker, 'get_mastery_summary'):
                try:
                    mastery_data = self.mastery_tracker.get_mastery_summary(username, course)
                    if mastery_data and mastery_data.get("total_interactions", 0) > 0:
                        print(f"DEBUG: 📊 Got mastery data from tracker")
                        return mastery_data  # Already formatted by tracker
                except Exception as e:
                    print(f"DEBUG: Mastery tracker failed: {e}")
            
            # Method 3: Direct Redis key access
            mastery_key = f"mastery:{username}:{course}"
            raw_data = self.redis_client.get_redis().get(mastery_key)
            if raw_data:
                print(f"DEBUG: 🔑 Got mastery data directly from Redis key")
                parsed_data = json.loads(raw_data)
                return self._format_mastery_data_fixed(parsed_data)
            
            print(f"DEBUG: ⚠️ No mastery data found for {username}:{course}")
            return {"go_masteries": {}, "week_masteries": {}, "total_interactions": 0}
            
        except Exception as e:
            print(f"DEBUG: Error getting fresh mastery data: {e}")
            return {"go_masteries": {}, "week_masteries": {}, "total_interactions": 0}

    def update_progress_quiz_safe(self, username: str, course: str, week: int, 
                                 quiz_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        SAFE: Update progress from quiz results with error handling
        This is the method being called from the Streamlit quiz interface
        """
        try:
            print(f"DEBUG: 🔄 QUIZ MASTERY: Safe progress update for {username} in {course} W{week}")
            
            # Extract quiz context information
            interaction_context = {
                "is_quiz": True,
                "correct": quiz_result.get("correct", False),
                "score": quiz_result.get("score", 0.0),
                "go_data": {
                    "go_id": quiz_result.get("go_id", f"GO_{week:02d}_01_01")
                },
                "quiz_result": quiz_result
            }
            
            print(f"DEBUG: 📝 Quiz context: correct={interaction_context['correct']}, score={interaction_context['score']}")
            
            # Use the existing update_progress_from_mastery method
            result = self.update_progress_from_mastery(
                username=username,
                course=course, 
                week=week,
                interaction_context=interaction_context
            )
            
            if result:
                print(f"DEBUG: ✅ QUIZ MASTERY: Progress update successful")
                return result
            else:
                print(f"DEBUG: ⚠️ QUIZ MASTERY: Progress update returned None")
                return {"progress_updated": False, "error": "No progress change detected"}
                
        except Exception as e:
            print(f"ERROR: ❌ QUIZ MASTERY: Progress bridge failed: {e}")
            import traceback
            traceback.print_exc()
            return {"progress_updated": False, "error": str(e)}
    
    def _format_mastery_data_fixed(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """FIXED: Format raw mastery data into expected structure"""
        try:
            # If already formatted, return as-is
            if "go_masteries" in raw_data and "week_masteries" in raw_data:
                return raw_data
            
            # Format raw data
            formatted_data = {
                "go_masteries": {},
                "lo_masteries": {},
                "week_masteries": {},
                "course_mastery": 0.0,
                "total_interactions": raw_data.get("total_interactions", 0),
                "last_session": raw_data.get("last_session", "")
            }
            
            # Extract GO masteries
            go_masteries_raw = raw_data.get("go_masteries", {})
            for go_id, mastery_info in go_masteries_raw.items():
                if isinstance(mastery_info, dict) and "level" in mastery_info:
                    formatted_data["go_masteries"][go_id] = mastery_info["level"]
                elif isinstance(mastery_info, (int, float)):
                    formatted_data["go_masteries"][go_id] = float(mastery_info)
                else:
                    print(f"DEBUG: Unknown mastery format for {go_id}: {mastery_info}")
                    formatted_data["go_masteries"][go_id] = 0.0
            
            # Extract week masteries
            week_masteries_raw = raw_data.get("week_masteries", {})
            for week_key, mastery_info in week_masteries_raw.items():
                week_num = int(week_key) if isinstance(week_key, str) else week_key
                if isinstance(mastery_info, dict) and "level" in mastery_info:
                    formatted_data["week_masteries"][week_num] = mastery_info["level"]
                elif isinstance(mastery_info, (int, float)):
                    formatted_data["week_masteries"][week_num] = float(mastery_info)
                else:
                    formatted_data["week_masteries"][week_num] = 0.0
            
            # Extract course mastery
            course_mastery_raw = raw_data.get("course_mastery", 0.0)
            if isinstance(course_mastery_raw, dict) and "level" in course_mastery_raw:
                formatted_data["course_mastery"] = course_mastery_raw["level"]
            else:
                formatted_data["course_mastery"] = float(course_mastery_raw)
            
            print(f"DEBUG: ✅ Formatted mastery data - GOs: {len(formatted_data['go_masteries'])}, Interactions: {formatted_data['total_interactions']}")
            return formatted_data
            
        except Exception as e:
            print(f"DEBUG: Error formatting mastery data: {e}")
            return {"go_masteries": {}, "week_masteries": {}, "total_interactions": 0}
    
    def _calculate_progress_from_mastery_enhanced_fixed(self, mastery_summary: Dict, current_week: int, 
                                                       context: Dict) -> Dict[str, Any]:
        """FIXED: Enhanced progress calculation with corrected variable names"""
        
        go_masteries = mastery_summary.get("go_masteries", {})
        week_masteries = mastery_summary.get("week_masteries", {})
        
        print(f"DEBUG: 📊 ENHANCED calculation - GO count: {len(go_masteries)}, Week masteries: {len(week_masteries)}")
        
        # Find GOs for current week (multiple patterns)
        week_gos = []
        week_patterns = [
            f"_{current_week:02d}_",  # GO_01_QUIZ_01
            f"GO_{current_week:02d}",  # GO_01_CONCEPT_01
            f"W{current_week}_",       # W1_CONCEPT_01
            f"WEEK_{current_week}_"    # WEEK_1_QUIZ_01
        ]
        
        for go_id, mastery_level in go_masteries.items():
            # Check if this GO belongs to current week
            for pattern in week_patterns:
                if pattern in go_id and "CHAT" not in go_id:
                    week_gos.append((go_id, mastery_level))
                    print(f"DEBUG: 🎯 Week {current_week} GO found: {go_id} = {mastery_level:.3f}")
                    break
        
        # FIXED: Corrected variable names in list comprehension
        completed_gos = len([go_id for go_id, mastery in week_gos if mastery >= self.GO_COMPLETION_THRESHOLD])
        total_gos = len(week_gos)
        
        print(f"DEBUG: 📈 Week {current_week} status: {completed_gos}/{total_gos} GOs completed (threshold: {self.GO_COMPLETION_THRESHOLD})")
        
        # ENHANCED: Multiple methods to calculate increment
        completion_increment = 0.0
        achievements = []
        calculation_method = "none"
        
        if total_gos > 0:
            
            # Method 1: Quiz-specific increment (original logic)
            if context.get("is_quiz") and context.get("correct"):
                current_go_id = context.get("go_data", {}).get("go_id")
                print(f"DEBUG: 🔍 Method 1 - Quiz completion check: {current_go_id}")
                
                if current_go_id and current_go_id in [go_id for go_id, _ in week_gos]:
                    current_mastery = go_masteries.get(current_go_id, 0.0)
                    print(f"DEBUG: 🎯 Current GO mastery: {current_go_id} = {current_mastery:.3f}")
                    
                    if current_mastery >= self.GO_COMPLETION_THRESHOLD:
                        completion_increment = 1.0 / total_gos
                        achievements.append(f"Completed: {current_go_id}")
                        calculation_method = "quiz_completion"
                        print(f"DEBUG: 🎉 Method 1 SUCCESS - GO completion: {completion_increment:.3f}")
            
            # Method 2: ANY newly completed GO (not just current question)
            if completion_increment == 0.0:
                print(f"DEBUG: 🔄 Method 2 - Check for any newly completed GOs")
                
                # Check if any GO just crossed the threshold
                newly_completed_gos = []
                for go_id, mastery_level in week_gos:
                    if mastery_level >= self.GO_COMPLETION_THRESHOLD:
                        # Could check against previous state, but for now assume any high mastery is "new"
                        if mastery_level >= 0.85:  # Very high mastery likely means recent completion
                            newly_completed_gos.append(go_id)
                
                if newly_completed_gos:
                    # Give credit for newly completed GOs
                    completion_increment = len(newly_completed_gos) * (1.0 / total_gos)
                    achievements.extend([f"Mastered: {go_id}" for go_id in newly_completed_gos])
                    calculation_method = "any_completion"
                    print(f"DEBUG: 🎉 Method 2 SUCCESS - New GOs completed: {len(newly_completed_gos)}, increment: {completion_increment:.3f}")
            
            # Method 3: Proportional progress based on overall mastery improvement
            if completion_increment == 0.0 and context.get("is_quiz"):
                print(f"DEBUG: 🔄 Method 3 - Proportional progress for any quiz activity")
                
                # Give small progress increment for any correct quiz answer
                if context.get("correct"):
                    completion_increment = 0.05 / total_gos  # 5% of a GO's worth
                    achievements.append("Learning Progress")
                    calculation_method = "proportional_quiz"
                    print(f"DEBUG: 🎉 Method 3 SUCCESS - Proportional increment: {completion_increment:.3f}")
            
            # Method 4: Tutor completion increment
            if completion_increment == 0.0 and context.get("is_tutor"):
                print(f"DEBUG: 🔄 Method 4 - Tutor session progress")
                
                if context.get("mastery_achieved"):
                    completion_increment = 1.0 / total_gos
                    achievements.append("Tutor Session Mastery")
                    calculation_method = "tutor_completion"
                    print(f"DEBUG: 🎉 Method 4 SUCCESS - Tutor increment: {completion_increment:.3f}")
        
        else:
            print(f"DEBUG: ⚠️ No GOs found for week {current_week} - checking all GOs for patterns")
            # Debug: show all available GO IDs
            for go_id in list(go_masteries.keys())[:10]:  # Show first 10
                print(f"DEBUG: Available GO: {go_id}")
        
        # Check for week mastery achievement
        week_mastery = week_masteries.get(current_week, 0.0)
        if week_mastery >= self.WEEK_COMPLETION_THRESHOLD:
            achievements.append(f"Week {current_week} Mastery Achieved!")
        
        result = {
            "completion_increment": completion_increment,
            "week_completion_rate": completed_gos / total_gos if total_gos > 0 else 0.0,
            "completed_gos": completed_gos,
            "total_gos": total_gos,
            "achievements": achievements,
            "week_mastery": week_mastery,
            "calculation_method": calculation_method
        }
        
        print(f"DEBUG: 📊 ENHANCED Progress calculation result: {result}")
        return result
    
    def _apply_progress_updates_enhanced(self, username: str, course: str, week: int, 
                                       progress_updates: Dict) -> Optional[Dict]:
        """FIXED: Enhanced progress updates with better error handling and verification"""
        
        try:
            completion_increment = progress_updates.get("completion_increment", 0.0)
            
            print(f"DEBUG: 📝 ENHANCED: Applying progress updates - increment: {completion_increment:.3f}")
            
            if completion_increment > 0.0:
                # STEP 1: Get current progress with detailed logging
                print(f"DEBUG: 🔍 Step 1: Getting current progress for {username}")
                current_progress = self.redis_client.get_user_progress(username)
                print(f"DEBUG: 📊 Raw current progress: {current_progress}")
                
                current_course_progress = current_progress.get(course, {})
                old_completion = current_course_progress.get("completion", 0.0)
                
                print(f"DEBUG: 📊 Current completion for {course}: {old_completion:.3f}")
                
                # STEP 2: Apply update with detailed logging
                print(f"DEBUG: 🔧 Step 2: Calling update_user_progress")
                print(f"DEBUG: 📋 Parameters:")
                print(f"   username: '{username}'")
                print(f"   course: '{course}'")
                print(f"   week: {week}")
                print(f"   increment_completion: {completion_increment}")
                
                try:
                    self.redis_client.update_user_progress(
                        username=username,
                        course=course,
                        week=week,
                        increment_completion=completion_increment
                    )
                    print(f"DEBUG: ✅ update_user_progress call completed without exception")
                    
                except Exception as update_error:
                    print(f"DEBUG: ❌ update_user_progress call failed: {update_error}")
                    raise update_error
                
                # STEP 3: Verify update with retry logic
                print(f"DEBUG: 🔍 Step 3: Verifying update (with retry)")
                
                # Wait a moment for Redis to process
                import time
                time.sleep(0.1)
                
                # Try to get updated progress multiple times
                updated_progress = None
                for attempt in range(3):
                    try:
                        updated_progress = self.redis_client.get_user_progress(username)
                        updated_course_progress = updated_progress.get(course, {})
                        new_completion = updated_course_progress.get("completion", 0.0)
                        
                        print(f"DEBUG: 📊 Attempt {attempt + 1} - New completion: {new_completion:.3f}")
                        
                        if abs(new_completion - old_completion) >= 0.001:
                            print(f"DEBUG: ✅ Progress change detected on attempt {attempt + 1}")
                            break
                        else:
                            print(f"DEBUG: ⚠️ No change detected on attempt {attempt + 1}, retrying...")
                            time.sleep(0.1)
                            
                    except Exception as verify_error:
                        print(f"DEBUG: ❌ Verification attempt {attempt + 1} failed: {verify_error}")
                        if attempt == 2:  # Last attempt
                            raise verify_error
                        time.sleep(0.1)
                
                if updated_progress:
                    new_completion = updated_progress.get(course, {}).get("completion", 0.0)
                    actual_change = new_completion - old_completion
                    
                    print(f"DEBUG: 📊 Final verification:")
                    print(f"   Old completion: {old_completion:.3f}")
                    print(f"   New completion: {new_completion:.3f}")
                    print(f"   Expected change: {completion_increment:.3f}")
                    print(f"   Actual change: {actual_change:.3f}")
                    print(f"   Change difference: {abs(actual_change - completion_increment):.3f}")
                    
                    if abs(actual_change - completion_increment) < 0.001:
                        print(f"DEBUG: ✅ ENHANCED: Progress update SUCCESSFUL!")
                        return updated_progress
                    else:
                        print(f"DEBUG: ⚠️ ENHANCED: Progress update PARTIAL - change detected but not as expected")
                        return updated_progress
                else:
                    print(f"DEBUG: ❌ ENHANCED: Could not retrieve updated progress")
            
            else:
                print(f"DEBUG: ℹ️ ENHANCED: No progress increment needed (increment: {completion_increment:.3f})")
            
            return None
            
        except Exception as e:
            print(f"ERROR: ENHANCED: Failed to apply progress updates: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_progress_from_fresh_mastery(self, username: str, course: str, week: int, 
                                         interaction_context: Dict[str, Any],
                                         fresh_mastery_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        FIXED: Update user progress using fresh mastery data (no stale cache)
        Use this when you have fresh mastery data to avoid cache issues
        """
        try:
            print(f"DEBUG: 🔄 ENHANCED: Updating progress from FRESH mastery for {username} in {course} W{week}")
            
            # Use the provided fresh mastery data and format it properly
            mastery_summary = self._format_mastery_data_fixed(fresh_mastery_summary)
            print(f"DEBUG: 📊 Using provided fresh data - GO count: {len(mastery_summary.get('go_masteries', {}))}")
            
            # Calculate progress updates using enhanced method
            progress_updates = self._calculate_progress_from_mastery_enhanced_fixed(
                mastery_summary, week, interaction_context
            )
            
            # Apply progress updates using enhanced method
            updated_progress = self._apply_progress_updates_enhanced(
                username, course, week, progress_updates
            )
            
            # Check for week advancement
            week_advancement = self._check_week_advancement(
                username, course, week, mastery_summary
            )
            
            result = {
                "progress_updated": updated_progress is not None,
                "completion_change": progress_updates.get("completion_increment", 0.0),
                "week_advanced": week_advancement.get("advanced", False),
                "next_week": week_advancement.get("next_week"),
                "achievements": progress_updates.get("achievements", []),
                "mastery_triggered": True,
                "used_fresh_data": True,
                "debug_info": {
                    "mastery_go_count": len(mastery_summary.get("go_masteries", {})),
                    "week_gos_found": progress_updates.get("total_gos", 0),
                    "completed_gos": progress_updates.get("completed_gos", 0),
                    "calculation_method": progress_updates.get("calculation_method", "unknown")
                }
            }
            
            print(f"DEBUG: ✅ ENHANCED FRESH Progress integration result: {result}")
            return result
            
        except Exception as e:
            print(f"ERROR: Enhanced fresh progress integration failed: {e}")
            import traceback
            traceback.print_exc()
            return {"progress_updated": False, "error": str(e)}
    
    def _check_week_advancement(self, username: str, course: str, current_week: int, 
                               mastery_summary: Dict) -> Dict[str, Any]:
        """Check if user should advance to next week based on mastery"""
        
        try:
            week_masteries = mastery_summary.get("week_masteries", {})
            current_week_mastery = week_masteries.get(current_week, 0.0)
            
            # Check if current week is sufficiently mastered
            if current_week_mastery >= self.WEEK_COMPLETION_THRESHOLD:
                
                # Get current progress to see if user is already on a later week
                current_progress = self.redis_client.get_user_progress(username)
                current_progress_week = current_progress.get(course, {}).get("week", 1)
                
                # Only advance if user hasn't already advanced beyond this week
                if current_progress_week <= current_week:
                    next_week = current_week + 1
                    
                    # Advance to next week
                    self.redis_client.update_user_progress(
                        username=username,
                        course=course,
                        week=next_week,
                        completion=0.0  # Reset completion for new week
                    )
                    
                    print(f"DEBUG: 🚀 Advanced {username} to week {next_week} (mastery: {current_week_mastery:.2f})")
                    
                    return {
                        "advanced": True,
                        "next_week": next_week,
                        "mastery_level": current_week_mastery
                    }
            
            return {"advanced": False}
            
        except Exception as e:
            print(f"ERROR: Week advancement check failed: {e}")
            return {"advanced": False, "error": str(e)}
    
    def get_progress_summary(self, username: str, course: str) -> Dict[str, Any]:
        """Get combined progress and mastery summary for UI display"""
        
        try:
            # Get user progress (completion percentages, week position)
            user_progress = self.redis_client.get_user_progress(username)
            course_progress = user_progress.get(course, {})
            
            # Get mastery summary using fresh data method
            mastery_summary = self._get_fresh_mastery_data_fixed(username, course)
            
            # Combine for comprehensive view
            combined_summary = {
                # Progress system data
                "current_week": course_progress.get("week", 1),
                "week_completion": course_progress.get("completion", 0.0),
                "last_updated": course_progress.get("last_updated", ""),
                
                # Mastery system data  
                "week_masteries": mastery_summary.get("week_masteries", {}),
                "go_masteries": mastery_summary.get("go_masteries", {}),
                "total_interactions": mastery_summary.get("total_interactions", 0),
                
                # Combined insights
                "overall_course_progress": self._calculate_overall_progress(mastery_summary),
                "ready_for_next_week": self._is_ready_for_next_week(mastery_summary, course_progress.get("week", 1)),
                "recent_achievements": self._get_recent_achievements(mastery_summary)
            }
            
            return combined_summary
            
        except Exception as e:
            print(f"ERROR: Failed to get progress summary: {e}")
            return {"error": str(e)}
    
    def _calculate_overall_progress(self, mastery_summary: Dict) -> float:
        """Calculate overall course progress based on mastery levels"""
        
        week_masteries = mastery_summary.get("week_masteries", {})
        if not week_masteries:
            return 0.0
        
        # Calculate weighted progress across all weeks
        total_mastery = sum(week_masteries.values())
        max_possible = len(week_masteries) * 1.0
        
        return total_mastery / max_possible if max_possible > 0 else 0.0
    
    def _is_ready_for_next_week(self, mastery_summary: Dict, current_week: int) -> bool:
        """Check if user is ready to advance to next week"""
        
        week_masteries = mastery_summary.get("week_masteries", {})
        current_week_mastery = week_masteries.get(current_week, 0.0)
        
        return current_week_mastery >= self.WEEK_COMPLETION_THRESHOLD
    
    def _get_recent_achievements(self, mastery_summary: Dict) -> List[str]:
        """Get list of recent achievements"""
        
        achievements = []
        go_masteries = mastery_summary.get("go_masteries", {})
        
        # Find recently mastered GOs (high mastery level)
        for go_id, mastery_level in go_masteries.items():
            if mastery_level >= 0.9:  # Very high mastery
                skill_name = go_id.replace("GO_", "").replace("_", " ")
                achievements.append(f"Mastered: {skill_name}")
        
        return achievements[:3]  # Return top 3 recent achievements