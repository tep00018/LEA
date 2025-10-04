# File: create_kc_model.py
"""
Create KC Model Script (Step 4)

This script converts the finalized XLSX KC model (after Step 3 edits) 
into the final JSON format for the LEA environment.

Usage:
    python create_kc_model.py <COURSE_CODE>
    
Example:
    python create_kc_model.py CMP511

Input: 
    - {COURSE_CODE}_Improved_KC_Model_Updated.xlsx (manually edited in Step 3)
    
Output:
    - KC_Model_{COURSE_CODE}.json (final JSON format for LEA)
    - KC_Model_{COURSE_CODE}_ui_navigation.json (UI navigation structure)
"""

import sys
import os
import pandas as pd
import json
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict
import ast
from pathlib import Path


class AgenticAITemplateConverter:
    """
    Converts course objectives XLSX to a comprehensive template structure
    suitable for agentic AI models with detailed LO and GO mappings.
    """
    
    def __init__(self):
        """Initialize the converter with cognitive level mappings and assessment types."""
        
        # Store course code for later use
        self.course_code = None
        
        # Cognitive levels based on Bloom's taxonomy for AI assessment
        self.cognitive_levels = {
            1: "Remember",      # Basic recall and recognition
            2: "Understand",    # Comprehension and explanation  
            3: "Apply",         # Using knowledge in new situations
            4: "Analyze",       # Breaking down and examining
            5: "Evaluate",      # Making judgments and critiques
            6: "Create"         # Synthesizing and producing new work
        }
        
        # Cognitive level name to number mapping
        self.cognitive_name_to_level = {
            "knowledge": 1, "remember": 1, "remembering": 1,
            "comprehension": 2, "understand": 2, "understanding": 2,
            "application": 3, "apply": 3, "applying": 3,
            "analysis": 4, "analyze": 4, "analyzing": 4,
            "synthesis": 5, "evaluate": 5, "evaluating": 5,
            "evaluation": 6, "create": 6, "creating": 6
        }
        
        # Assessment types for different skill categories
        self.assessment_types = {
            "conceptual": ["multiple_choice", "short_answer", "concept_mapping"],
            "procedural": ["step_by_step", "implementation", "debugging"],
            "analytical": ["case_study", "comparison", "evaluation"],
            "creative": ["project", "design", "synthesis"]
        }
        
        # Skill complexity indicators for AI model guidance
        self.complexity_indicators = {
            "basic": {"tokens_required": 50, "context_depth": "shallow", "examples_needed": 1},
            "intermediate": {"tokens_required": 150, "context_depth": "moderate", "examples_needed": 2},
            "advanced": {"tokens_required": 300, "context_depth": "deep", "examples_needed": 3},
            "expert": {"tokens_required": 500, "context_depth": "comprehensive", "examples_needed": 4}
        }

    def load_course_objectives_xlsx(self, xlsx_file_path: str) -> Dict[str, Any]:
        """Load the course objectives from XLSX file."""
        try:
            # Try reading the Complete_KC_Model sheet first, then default sheet
            try:
                df = pd.read_excel(xlsx_file_path, sheet_name='Complete_KC_Model')
                print(f"✅ Successfully loaded from 'Complete_KC_Model' sheet")
            except:
                df = pd.read_excel(xlsx_file_path)
                print(f"✅ Successfully loaded from default sheet")
            
            print(f"📊 XLSX file contains {len(df)} rows")
            
            # Get basic course information
            course_code = df['Module'].iloc[0] if 'Module' in df.columns else "Unknown"
            course_name = df['Module Name'].iloc[0] if 'Module Name' in df.columns else "Unknown Course"
            
            # Store course code as instance variable for later use
            self.course_code = course_code
            
            print(f"📚 Course: {course_code} - {course_name}")
            
            # Convert DataFrame to structured format
            course_data = self._convert_xlsx_to_structured_format(df, course_code, course_name)
            
            return course_data
            
        except Exception as e:
            print(f"❌ Error loading XLSX file: {e}")
            raise

    def _parse_list_column(self, value):
        """Parse list-like string columns safely."""
        if pd.isna(value) or value == '':
            return []
        
        if isinstance(value, str):
            # Try to parse as Python literal
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return parsed
                else:
                    return [parsed]
            except:
                # If that fails, split by comma and clean
                return [item.strip().strip("'\"") for item in value.split(',') if item.strip()]
        
        return value if isinstance(value, list) else [value]

    def _get_cognitive_level_number(self, cognitive_level_str: str) -> int:
        """Convert cognitive level string to number."""
        if pd.isna(cognitive_level_str):
            return 2
        
        level_str = str(cognitive_level_str).lower().strip()
        return self.cognitive_name_to_level.get(level_str, 2)

    def _convert_xlsx_to_structured_format(self, df: pd.DataFrame, course_code: str, course_name: str) -> Dict[str, Any]:
        """Convert the XLSX DataFrame to the structured format expected by the rest of the code."""
        
        # Group by week and learning objective
        objectives = []
        weeks_data = defaultdict(lambda: defaultdict(list))
        
        # First, let's extract unique week names for mapping
        week_names_map = {}
        for _, row in df.iterrows():
            week_num = row.get('week_number', row.get('Week #', 1))
            # Try multiple possible column names for week name
            week_name = (row.get('Week Name') or 
                        row.get('week_name') or 
                        row.get('WeekName') or 
                        f'Week {week_num}')
            
            if week_num and week_name and week_num not in week_names_map:
                # Clean the week name - remove any "Week X:" prefix if present
                clean_week_name = str(week_name).strip()
                if clean_week_name.startswith(f'Week {week_num}:'):
                    clean_week_name = clean_week_name.replace(f'Week {week_num}:', '').strip()
                elif clean_week_name.startswith(f'W{week_num:02d}'):
                    clean_week_name = clean_week_name.replace(f'W{week_num:02d}', '').strip()
                
                week_names_map[week_num] = clean_week_name
    
        print(f"📅 Extracted week names: {week_names_map}")
        
        # Organize data by week and learning objective
        for _, row in df.iterrows():
            week_num = row.get('week_number', row.get('Week #', 1))
            
            # Parse week number if it's in format "W01"
            if isinstance(week_num, str) and week_num.startswith('W'):
                week_num = int(week_num[1:])
            
            lo_name = row.get('Learning Objective Name', 'Unknown LO')
            go_name = row.get('Granular Objective Name', 'Unknown GO')
            
            # Get the clean week name from our mapping
            week_name = week_names_map.get(week_num, f'Week {week_num}')
            
            weeks_data[week_num][lo_name].append({
                'go_name': go_name,
                'cognitive_level': row.get('cognitive_level', 'Comprehension'),
                'estimated_difficulty': row.get('estimated_difficulty', 2),
                'conceptual_tags': self._parse_list_column(row.get('conceptual_tags', [])),
                'prerequisite_concepts': self._parse_list_column(row.get('prerequisite_concepts', [])),
                'mastery_threshold': row.get('mastery_threshold', 0.7),
                'threshold_rationale': row.get('threshold_rationale', ''),
                'week_name': week_name,  # Use the clean week name
                'lecture_number': row.get('lecture_number', 'A')
            })
        
        # Convert to the expected objectives format
        for week_num in sorted(weeks_data.keys()):
            week_los = weeks_data[week_num]
            
            for lo_name, gos in week_los.items():
                # Calculate average difficulty and time for the LO
                avg_difficulty = sum(go['estimated_difficulty'] for go in gos) / len(gos)
                estimated_time = len(gos) * 15  # 15 minutes per GO as base estimate
                
                # Get prerequisite weeks (weeks that contain prerequisite concepts)
                prerequisite_weeks = set()
                for go in gos:
                    prereq_concepts = go['prerequisite_concepts']
                    for prereq_week, prereq_los in weeks_data.items():
                        if prereq_week < week_num:  # Only look at earlier weeks
                            for prereq_lo_name, prereq_gos in prereq_los.items():
                                for prereq_go in prereq_gos:
                                    if any(concept in prereq_go['go_name'] or concept in prereq_go.get('conceptual_tags', []) 
                                          for concept in prereq_concepts):
                                        prerequisite_weeks.add(prereq_week)
                
                # Create objective entry with proper week name
                objective = {
                    "week": int(week_num),
                    "title": lo_name,
                    "description": f"Learning objective covering: {', '.join([go['go_name'] for go in gos])}",
                    "difficulty_level": int(round(avg_difficulty)),
                    "estimated_time_minutes": estimated_time,
                    "prerequisite_weeks": sorted(list(prerequisite_weeks)),
                    "granular_skills": [go['go_name'] for go in gos],
                    "week_name": gos[0]['week_name'],  # This will now be the clean name like "Introduction"
                    "cognitive_levels": [self._get_cognitive_level_number(go['cognitive_level']) for go in gos],
                    "mastery_thresholds": [go['mastery_threshold'] for go in gos],
                    "conceptual_tags": list(set(tag for go in gos for tag in go['conceptual_tags'])),
                    "granular_objectives_data": gos  # Store the detailed GO data
                }
                
                objectives.append(objective)
        
        # Calculate summary statistics
        total_weeks = max(obj["week"] for obj in objectives) if objectives else 0
        total_skills = sum(len(obj["granular_skills"]) for obj in objectives)
        difficulty_levels = [obj["difficulty_level"] for obj in objectives]
        difficulty_range = f"{min(difficulty_levels)}-{max(difficulty_levels)}" if difficulty_levels else "1-5"
        
        course_data = {
            "course_code": course_code,
            "course_name": course_name,
            "objectives": objectives,
            "summary": {
                "total_weeks": total_weeks,
                "total_skills": total_skills,
                "difficulty_range": difficulty_range,
                "total_learning_objectives": len(objectives)
            }
        }
        
        print(f"🎯 Converted to {len(objectives)} learning objectives with {total_skills} granular skills")
        
        return course_data
        

    def extract_skill_category(self, skill_name: str) -> str:
        """Determine the category of a skill based on its name and context."""
        
        skill_lower = skill_name.lower()
        
        # Categorize based on common patterns in skill names
        if any(term in skill_lower for term in ['implementation', 'creation', 'application', 'utilization', 'implement', 'create', 'build']):
            return "procedural"
        elif any(term in skill_lower for term in ['analysis', 'comparison', 'evaluation', 'recognition', 'analyze', 'compare', 'evaluate', 'identify', 'classify']):
            return "analytical"
        elif any(term in skill_lower for term in ['design', 'composition', 'generation', 'synthesis', 'develop', 'formulate']):
            return "creative"
        else:
            return "conceptual"

    def determine_complexity_level(self, difficulty: int, estimated_time: int, cognitive_level: int = 2) -> str:
        """Determine complexity level based on difficulty, time requirements, and cognitive level."""
        
        # Combine difficulty rating, time, and cognitive level to determine complexity
        complexity_score = (difficulty * 0.5) + (estimated_time / 60 * 0.2) + (cognitive_level * 0.3)
        
        if complexity_score <= 2.5:
            return "basic"
        elif complexity_score <= 3.5:
            return "intermediate"
        elif complexity_score <= 4.5:
            return "advanced"
        else:
            return "expert"

    def generate_assessment_strategies(self, skill_name: str, skill_category: str, 
                                     cognitive_level: str, complexity: str, mastery_threshold: float = 0.7) -> List[Dict]:
        """Generate appropriate assessment strategies for each granular skill."""
        
        assessments = []
        base_assessments = self.assessment_types.get(skill_category, ["multiple_choice"])
        
        for assessment_type in base_assessments[:2]:  # Limit to 2 assessments per skill
            
            # Determine assessment parameters based on complexity
            complexity_info = self.complexity_indicators[complexity]
            
            assessment = {
                "type": assessment_type,
                "cognitive_level": cognitive_level,
                "estimated_duration_minutes": max(5, complexity_info["tokens_required"] // 20),
                "difficulty_weight": complexity_info["context_depth"],
                "mastery_threshold": mastery_threshold,
                "adaptive_parameters": {
                    "success_threshold": mastery_threshold,
                    "retry_limit": 3 if complexity in ["basic", "intermediate"] else 2,
                    "hint_availability": complexity in ["basic", "intermediate"],
                    "collaborative_allowed": complexity == "expert"
                },
                "ai_generation_context": {
                    "max_tokens": complexity_info["tokens_required"],
                    "context_depth": complexity_info["context_depth"],
                    "examples_required": complexity_info["examples_needed"],
                    "domain_focus": self.course_code.lower() if self.course_code else "general",
                    "technical_level": complexity
                }
            }
            
            assessments.append(assessment)
        
        return assessments

    def create_prerequisite_graph(self, objectives: List[Dict]) -> Dict[str, List[str]]:
        """Create a prerequisite dependency graph for the agentic AI model."""
        
        prerequisite_graph = {}
        
        for obj in objectives:
            week = obj["week"]
            title = obj["title"]
            prerequisites = []
            
            # Convert prerequisite weeks to specific learning objective dependencies
            for prereq_week in obj.get("prerequisite_weeks", []):
                prereq_objectives = [o["title"] for o in objectives if o["week"] == prereq_week]
                prerequisites.extend(prereq_objectives)
            
            prerequisite_graph[title] = prerequisites
        
        return prerequisite_graph

    def generate_learning_pathways(self, objectives: List[Dict]) -> List[Dict]:
        """Generate adaptive learning pathways for the agentic AI model."""
        
        pathways = []
        
        # Group weeks into logical pathways
        max_week = max(obj["week"] for obj in objectives) if objectives else 0
        
        if max_week <= 4:
            # Short course - create 2 pathways
            pathway_groups = {
                "foundations": list(range(1, (max_week // 2) + 2)),
                "advanced_concepts": list(range((max_week // 2) + 2, max_week + 1))
            }
        else:
            # Longer course - create 4 pathways
            quarter = max_week // 4
            pathway_groups = {
                "foundations": list(range(1, quarter + 2)),
                "core_concepts": list(range(quarter + 2, (quarter * 2) + 2)),
                "advanced_topics": list(range((quarter * 2) + 2, (quarter * 3) + 2)),
                "specialized_applications": list(range((quarter * 3) + 2, max_week + 1))
            }
        
        for pathway_name, weeks in pathway_groups.items():
            if not weeks:  # Skip empty pathways
                continue
                
            pathway_objectives = [obj for obj in objectives if obj["week"] in weeks]
            
            if not pathway_objectives:  # Skip if no objectives in this pathway
                continue
            
            pathway = {
                "pathway_id": f"pathway_{pathway_name}",
                "name": pathway_name.replace("_", " ").title(),
                "description": f"Learning pathway focusing on {pathway_name.replace('_', ' ')}",
                "objectives": [obj["title"] for obj in pathway_objectives],
                "weeks": weeks,
                "estimated_completion_time": sum(obj["estimated_time_minutes"] for obj in pathway_objectives),
                "difficulty_progression": [obj["difficulty_level"] for obj in pathway_objectives],
                "adaptive_rules": {
                    "prerequisite_mastery_threshold": 0.8,
                    "advancement_criteria": "mastery_based",
                    "remediation_triggers": ["low_performance", "time_exceeded"],
                    "acceleration_triggers": ["high_mastery", "rapid_completion"]
                }
            }
            
            pathways.append(pathway)
        
        return pathways

    def _generate_granular_objective_description(self, skill_name: str, skill_category: str, 
                                               cognitive_level: str, conceptual_tags: List[str], 
                                               parent_lo_title: str) -> str:
        """Generate a detailed description for a granular objective based on its properties."""
        
        # Create action verbs based on cognitive level
        action_verbs = {
            "Remember": ["recall", "identify", "list", "name", "recognize"],
            "Understand": ["explain", "describe", "interpret", "summarize", "classify"],
            "Apply": ["implement", "use", "demonstrate", "apply", "execute"],
            "Analyze": ["analyze", "compare", "examine", "break down", "differentiate"],
            "Evaluate": ["assess", "critique", "evaluate", "judge", "validate"],
            "Create": ["design", "develop", "create", "synthesize", "generate"]
        }
        
        # Get appropriate action verb
        verbs = action_verbs.get(cognitive_level, ["understand"])
        primary_verb = verbs[0]
        
        # Clean and format skill name
        clean_skill = skill_name.replace("_", " ").lower()
        
        # Generate description based on skill category and cognitive level
        if skill_category == "conceptual":
            if cognitive_level in ["Remember", "Understand"]:
                description = f"Students will {primary_verb} the concept of {clean_skill} and its role in {parent_lo_title.lower()}."
            else:
                description = f"Students will {primary_verb} {clean_skill} concepts to demonstrate understanding of {parent_lo_title.lower()}."
                
        elif skill_category == "procedural":
            if cognitive_level in ["Apply", "Create"]:
                description = f"Students will {primary_verb} {clean_skill} procedures and techniques in practical scenarios."
            else:
                description = f"Students will {primary_verb} the steps and methods involved in {clean_skill}."
                
        elif skill_category == "analytical":
            if cognitive_level in ["Analyze", "Evaluate"]:
                description = f"Students will {primary_verb} {clean_skill} by examining components and relationships."
            else:
                description = f"Students will {primary_verb} how to perform {clean_skill} in various contexts."
                
        else:  # creative
            if cognitive_level in ["Create", "Evaluate"]:
                description = f"Students will {primary_verb} solutions using {clean_skill} approaches and methods."
            else:
                description = f"Students will {primary_verb} {clean_skill} concepts and their applications."
        
        # Add conceptual context if available
        if conceptual_tags:
            # Filter out generic tags and focus on specific concepts
            specific_tags = [tag for tag in conceptual_tags if len(tag) > 5 and not tag.lower().startswith('basic')]
            if specific_tags:
                description += f" This includes understanding {', '.join(specific_tags[:2])}."
        
        return description

    def _generate_tutoring_guidance(self, skill_name: str, skill_category: str, 
                                  cognitive_level: str, description: str) -> Dict[str, Any]:
        """Generate comprehensive tutoring guidance for a granular objective."""
        
        # Get action verb from cognitive level
        action_verbs = {
            "Remember": "recall", "Understand": "explain", "Apply": "implement",
            "Analyze": "analyze", "Evaluate": "evaluate", "Create": "create"
        }
        
        primary_verb = action_verbs.get(cognitive_level, "understand")
        clean_skill = skill_name.replace("_", " ").lower()
        
        return {
            "primary_focus": description,
            "learning_outcomes": f"After completing this objective, students should be able to {primary_verb} {clean_skill} effectively.",
            "common_misconceptions": self._identify_common_misconceptions(skill_name, skill_category),
            "teaching_strategies": self._suggest_teaching_strategies(skill_category, cognitive_level),
            "assessment_focus": f"Assess student ability to {primary_verb} {clean_skill} at the {cognitive_level.lower()} level."
        }

    def _identify_common_misconceptions(self, skill_name: str, skill_category: str) -> List[str]:
        """Identify common misconceptions based on skill type."""
        
        skill_lower = skill_name.lower()
        misconceptions = []
        
        # AI/ML specific misconceptions
        if "ai" in skill_lower or "artificial intelligence" in skill_lower:
            misconceptions.extend([
                "AI and ML are the same thing",
                "AI can think like humans",
                "All AI systems learn automatically"
            ])
        
        if "machine learning" in skill_lower or "ml" in skill_lower:
            misconceptions.extend([
                "More data always leads to better models",
                "ML models are always objective and unbiased",
                "Complex models are always better"
            ])
        
        if "neural network" in skill_lower:
            misconceptions.extend([
                "Neural networks work exactly like the human brain",
                "More layers always improve performance",
                "Neural networks are black boxes that cannot be interpreted"
            ])
        
        # Category-based misconceptions
        if skill_category == "conceptual":
            misconceptions.extend([
                "Confusing correlation with causation",
                "Misunderstanding the scope of applicability"
            ])
        elif skill_category == "procedural":
            misconceptions.extend([
                "Skipping validation steps",
                "Misunderstanding parameter tuning effects"
            ])
        elif skill_category == "analytical":
            misconceptions.extend([
                "Over-interpreting results",
                "Ignoring assumption violations"
            ])
        
        return misconceptions[:3]  # Limit to top 3

    def _suggest_teaching_strategies(self, skill_category: str, cognitive_level: str) -> List[str]:
        """Suggest appropriate teaching strategies based on skill category and cognitive level."""
        
        strategies = []
        
        # Base strategies by cognitive level
        if cognitive_level in ["Remember", "Understand"]:
            strategies.extend([
                "Use visual diagrams and concept maps",
                "Provide clear definitions with examples",
                "Use analogies to familiar concepts"
            ])
        elif cognitive_level in ["Apply", "Analyze"]:
            strategies.extend([
                "Provide hands-on practice exercises",
                "Use case studies and real-world examples",
                "Encourage step-by-step problem solving"
            ])
        else:  # Evaluate, Create
            strategies.extend([
                "Facilitate project-based learning",
                "Encourage critical thinking discussions",
                "Provide open-ended challenges"
            ])
        
        # Additional strategies by skill category
        if skill_category == "procedural":
            strategies.append("Demonstrate procedures with guided practice")
        elif skill_category == "analytical":
            strategies.append("Use comparative analysis exercises")
        elif skill_category == "creative":
            strategies.append("Encourage experimentation and iteration")
        
        return strategies[:3]  # Limit to top 3

    def convert_to_agentic_template(self, course_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert the course objectives to a comprehensive agentic AI template
        with detailed LO and GO mappings.
        """
        
        print("🔄 Converting to agentic AI template...")
        
        objectives = course_data["objectives"]
        
        # Create the comprehensive template structure
        agentic_template = {
            "metadata": {
                "course_code": course_data["course_code"],
                "course_name": course_data.get("course_name", "Unknown Course"),
                "template_version": "2.1",
                "generated_timestamp": datetime.now().isoformat(),
                "total_learning_objectives": len(objectives),
                "total_granular_objectives": course_data["summary"]["total_skills"],
                "difficulty_range": course_data["summary"]["difficulty_range"],
                "estimated_total_time_hours": sum(obj["estimated_time_minutes"] for obj in objectives) / 60,
                "ai_model_requirements": {
                    "minimum_context_window": 4000,
                    "recommended_model_size": "medium",
                    "domain_specialization": f"{course_data['course_code'].lower()}_education",
                    "adaptive_capabilities_required": True
                }
            },
            
            "course_structure": {
                "prerequisite_graph": self.create_prerequisite_graph(objectives),
                "learning_pathways": self.generate_learning_pathways(objectives),
                "week_progression": [obj["week"] for obj in objectives]
            },
            
            "learning_objectives": [],
            "granular_objectives": [],
            
            "assessment_framework": {
                "cognitive_levels": self.cognitive_levels,
                "assessment_types": self.assessment_types,
                "complexity_indicators": self.complexity_indicators,
                "adaptive_parameters": {
                    "mastery_threshold_range": [0.6, 0.9],
                    "difficulty_adjustment_factor": 0.1,
                    "time_limit_flexibility": 0.2,
                    "hint_system_enabled": True
                }
            },
            
            "ai_agent_instructions": {
                "content_generation": {
                    "style": "educational_conversational",
                    "technical_level": "adaptive_to_student",
                    "explanation_depth": "scaffolded",
                    "example_requirements": "context_specific"
                },
                "assessment_generation": {
                    "question_variety": ["conceptual", "procedural", "analytical"],
                    "difficulty_calibration": "student_performance_based",
                    "feedback_style": "constructive_detailed",
                    "hint_generation": "progressive_disclosure"
                },
                "interaction_patterns": {
                    "questioning_strategy": "socratic_method",
                    "error_handling": "misconception_addressing",
                    "motivation_techniques": ["progress_tracking", "achievement_recognition"],
                    "personalization_factors": ["learning_style", "pace", "interests"]
                }
            }
        }
        
        # Process each learning objective
        for lo_idx, objective in enumerate(objectives, 1):
            
            avg_cognitive_level = sum(objective.get("cognitive_levels", [2])) / len(objective.get("cognitive_levels", [2]))
            complexity = self.determine_complexity_level(
                objective["difficulty_level"], 
                objective["estimated_time_minutes"],
                int(avg_cognitive_level)
            )
            
            cognitive_level = self.cognitive_levels.get(int(avg_cognitive_level), "Understand")
            
            # Create Learning Objective (LO) entry
            lo_entry = {
                "lo_id": f"LO_{objective['week']:02d}_{lo_idx:02d}",
                "week": objective["week"],
                "week_name": objective.get("week_name", f"Week {objective['week']}"),
                "title": objective["title"],
                "description": objective["description"],
                "cognitive_level": cognitive_level,
                "difficulty_level": objective["difficulty_level"],
                "complexity": complexity,
                "estimated_time_minutes": objective["estimated_time_minutes"],
                "prerequisite_weeks": objective["prerequisite_weeks"],
                "granular_skills_count": len(objective["granular_skills"]),
                "granular_skill_ids": [
                    f"GO_{objective['week']:02d}_{lo_idx:02d}_{go_idx:03d}" 
                    for go_idx in range(1, len(objective["granular_skills"]) + 1)
                ],
                "conceptual_tags": objective.get("conceptual_tags", []),
                "ai_context": {
                    "domain_keywords": self.extract_domain_keywords(objective["title"], objective["description"]),
                    "teaching_approach": "guided_discovery" if complexity in ["basic", "intermediate"] else "problem_based",
                    "assessment_weight": 0.8 if complexity == "expert" else 0.6,
                    "prerequisite_enforcement": "strict" if complexity in ["advanced", "expert"] else "flexible"
                }
            }
            
            agentic_template["learning_objectives"].append(lo_entry)
            
            # Create Granular Objective (GO) entries for each skill
            granular_data = objective.get("granular_objectives_data", [])
            
            for go_idx, skill in enumerate(objective["granular_skills"], 1):
                
                skill_category = self.extract_skill_category(skill)
                
                # Get specific data for this GO if available
                go_data = granular_data[go_idx - 1] if go_idx - 1 < len(granular_data) else {}
                go_cognitive_level = self._get_cognitive_level_number(go_data.get('cognitive_level', 'Comprehension'))
                go_mastery_threshold = go_data.get('mastery_threshold', 0.7)
                go_difficulty = go_data.get('estimated_difficulty', objective["difficulty_level"])
                
                # Generate a detailed description for the granular objective
                go_description = self._generate_granular_objective_description(
                    skill, skill_category, self.cognitive_levels.get(go_cognitive_level, "Understand"),
                    go_data.get('conceptual_tags', []), objective["title"]
                )
                
                # Generate tutoring guidance
                cognitive_level_name = self.cognitive_levels.get(go_cognitive_level, "Understand")
                tutoring_guidance = self._generate_tutoring_guidance(
                    skill, skill_category, cognitive_level_name, go_description
                )
                
                assessments = self.generate_assessment_strategies(
                    skill, skill_category, cognitive_level_name, 
                    complexity, go_mastery_threshold
                )
                
                go_entry = {
                    "go_id": f"GO_{objective['week']:02d}_{lo_idx:02d}_{go_idx:03d}",
                    "parent_lo_id": f"LO_{objective['week']:02d}_{lo_idx:02d}",
                    "skill_name": skill,
                    "skill_display_name": skill.replace("_", " ").title(),
                    "description": go_description,
                    "skill_category": skill_category,
                    "cognitive_level": cognitive_level_name,
                    "cognitive_level_number": go_cognitive_level,
                    "complexity": complexity,
                    "estimated_time_minutes": objective["estimated_time_minutes"] // len(objective["granular_skills"]),
                    "estimated_difficulty": go_difficulty,
                    "mastery_threshold": go_mastery_threshold,
                    "threshold_rationale": go_data.get('threshold_rationale', ''),
                    "conceptual_tags": go_data.get('conceptual_tags', []),
                    "prerequisite_concepts": go_data.get('prerequisite_concepts', []),
                    "tutoring_guidance": tutoring_guidance,
                    
                    "assessment_strategies": assessments,
                    
                    "ai_generation_parameters": {
                        "content_focus": skill_category,
                        "explanation_style": "step_by_step" if skill_category == "procedural" else "conceptual",
                        "example_complexity": complexity,
                        "interaction_mode": "guided" if complexity == "basic" else "exploratory",
                        "remediation_available": True,
                        "extension_activities": complexity in ["advanced", "expert"]
                    },
                    
                    "adaptive_rules": {
                        "prerequisite_check": len(objective["prerequisite_weeks"]) > 0,
                        "difficulty_adjustment": {
                            "success_rate_threshold": 0.8,
                            "failure_rate_threshold": 0.3,
                            "adjustment_magnitude": 0.1
                        },
                        "personalization": {
                            "learning_style_adaptation": True,
                            "pace_adjustment": True,
                            "interest_integration": skill_category in ["creative", "analytical"]
                        }
                    }
                }
                
                agentic_template["granular_objectives"].append(go_entry)
        
        return agentic_template

    def extract_domain_keywords(self, title: str, description: str) -> List[str]:
        """Extract domain-specific keywords for AI context."""
        
        combined_text = f"{title} {description}".lower()
        
        ml_keywords = [
            "machine learning", "neural network", "classification", "regression", 
            "supervised", "unsupervised", "deep learning", "cnn", "rnn", "lstm",
            "gradient descent", "backpropagation", "feature", "algorithm", "model",
            "training", "validation", "optimization", "clustering", "svm", "pca",
            "transformer", "attention", "perceptron", "artificial intelligence",
            "data mining", "pattern recognition", "ensemble", "overfitting"
        ]
        
        found_keywords = [keyword for keyword in ml_keywords if keyword in combined_text]
        return found_keywords[:5]  # Limit to top 5 keywords

    def generate_ui_navigation_structure(self, agentic_template: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a UI-friendly navigation structure for week → LO dropdown menus."""
        
        ui_structure = {
            "course_info": {
                "course_code": agentic_template["metadata"]["course_code"],
                "course_name": agentic_template["metadata"]["course_name"],
                "total_weeks": max(lo["week"] for lo in agentic_template["learning_objectives"])
            },
            "week_navigation": {},
            "quick_lookup": {
                "lo_by_id": {},
                "go_by_id": {},
                "week_by_lo_id": {}
            }
        }
        
        # Group LOs by week for dropdown navigation
        week_structure = defaultdict(list)
        
        for lo in agentic_template["learning_objectives"]:
            week_num = lo["week"]
            week_name = lo.get("week_name", f"Week {week_num}")
            
            # Get all GOs for this LO
            related_gos = [go for go in agentic_template["granular_objectives"] 
                          if go["parent_lo_id"] == lo["lo_id"]]
            
            lo_data = {
                "lo_id": lo["lo_id"],
                "title": lo["title"],
                "description": lo["description"],
                "estimated_time_minutes": lo["estimated_time_minutes"],
                "difficulty_level": lo["difficulty_level"],
                "complexity": lo["complexity"],
                "granular_objectives_count": len(related_gos),
                "granular_objectives": [
                    {
                        "go_id": go["go_id"],
                        "skill_name": go["skill_display_name"],
                        "description": go["description"],
                        "cognitive_level": go["cognitive_level"],
                        "mastery_threshold": go["mastery_threshold"],
                        "estimated_time_minutes": go["estimated_time_minutes"],
                        "skill_category": go["skill_category"],
                        "complexity": go["complexity"],
                        "conceptual_tags": go.get("conceptual_tags", []),
                        "prerequisite_concepts": go.get("prerequisite_concepts", [])
                    }
                    for go in related_gos
                ],
                "prerequisites": lo.get("prerequisite_weeks", []),
                "conceptual_tags": lo.get("conceptual_tags", []),
                "week_name": week_name  # Store the clean week name
            }
            
            week_structure[week_num].append(lo_data)
            
            # Add to quick lookup
            ui_structure["quick_lookup"]["lo_by_id"][lo["lo_id"]] = lo_data
            ui_structure["quick_lookup"]["week_by_lo_id"][lo["lo_id"]] = {
                "week_number": week_num,
                "week_name": week_name
            }
        
        # Create week navigation structure
        for week_num in sorted(week_structure.keys()):
            # Get the clean week name from the first LO in this week
            clean_week_name = week_structure[week_num][0]["week_name"]
            
            # Create a proper display name
            if clean_week_name.startswith(f"Week {week_num}"):
                # If it already starts with "Week X", use as is
                week_display = clean_week_name
            else:
                # Create format "Week X: Clean Name"
                week_display = f"Week {week_num}: {clean_week_name}"
            
            ui_structure["week_navigation"][f"week_{week_num:02d}"] = {
                "week_number": week_num,
                "week_name": clean_week_name,
                "week_display": week_display,  # This will now be "Week 1: Introduction"
                "learning_objectives": [
                    {
                        "lo_id": lo["lo_id"],
                        "title": lo["title"],
                        "short_title": lo["title"][:50] + "..." if len(lo["title"]) > 50 else lo["title"],
                        "description": lo["description"],
                        "granular_count": lo["granular_objectives_count"],
                        "estimated_time": lo["estimated_time_minutes"],
                        "difficulty": lo["difficulty_level"],
                        "complexity": lo["complexity"],
                        "granular_objectives": lo["granular_objectives"]  # Add the full GO details
                    }
                    for lo in week_structure[week_num]
                ],
                "total_time_minutes": sum(lo["estimated_time_minutes"] for lo in week_structure[week_num]),
                "total_granular_objectives": sum(lo["granular_objectives_count"] for lo in week_structure[week_num])
            }
        
        # Add granular objectives to quick lookup
        for go in agentic_template["granular_objectives"]:
            ui_structure["quick_lookup"]["go_by_id"][go["go_id"]] = {
                "go_id": go["go_id"],
                "parent_lo_id": go["parent_lo_id"],
                "skill_name": go["skill_display_name"],
                "description": go["description"],
                "cognitive_level": go["cognitive_level"],
                "complexity": go["complexity"],
                "mastery_threshold": go["mastery_threshold"],
                "estimated_time_minutes": go["estimated_time_minutes"],
                "skill_category": go["skill_category"],
                "conceptual_tags": go.get("conceptual_tags", []),
                "prerequisite_concepts": go.get("prerequisite_concepts", []),
                "assessment_types": [assess["type"] for assess in go["assessment_strategies"]]
            }
        
        return ui_structure
        

    def export_template(self, agentic_template: Dict[str, Any], 
                       output_filename: str = "agentic_ai_template.json"):
        """Export the agentic AI template to JSON file."""
        
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(agentic_template, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Agentic AI template exported to: {output_filename}")
            
            # Generate and export UI navigation structure
            ui_structure = self.generate_ui_navigation_structure(agentic_template)
            ui_filename = output_filename.replace('.json', '_ui_navigation.json')
            
            with open(ui_filename, 'w', encoding='utf-8') as f:
                json.dump(ui_structure, f, indent=2, ensure_ascii=False)
            
            print(f"✅ UI navigation structure exported to: {ui_filename}")
            
            # Display summary statistics
            metadata = agentic_template["metadata"]
            print(f"\n📊 TEMPLATE SUMMARY:")
            print(f"Course: {metadata['course_code']} - {metadata['course_name']}")
            print(f"Learning Objectives: {metadata['total_learning_objectives']}")
            print(f"Granular Objectives: {metadata['total_granular_objectives']}")
            print(f"Total Estimated Time: {metadata['estimated_total_time_hours']:.1f} hours")
            print(f"Learning Pathways: {len(agentic_template['course_structure']['learning_pathways'])}")
            
            # Show week structure for UI
            print(f"\n📋 UI NAVIGATION STRUCTURE:")
            for week_key, week_data in ui_structure["week_navigation"].items():
                print(f"  {week_data['week_display']} ({len(week_data['learning_objectives'])} LOs)")
                for lo in week_data['learning_objectives']:
                    print(f"    └─ {lo['short_title']} ({lo['granular_count']} GOs)")
            
            # Show cognitive distribution
            cognitive_dist = {}
            for go in agentic_template["granular_objectives"]:
                level = go["cognitive_level"]
                cognitive_dist[level] = cognitive_dist.get(level, 0) + 1
            
            print(f"\n🧠 Cognitive Level Distribution:")
            for level, count in cognitive_dist.items():
                percentage = (count / len(agentic_template["granular_objectives"])) * 100
                print(f"  {level}: {count} ({percentage:.1f}%)")
            
            # Show complexity distribution
            complexity_dist = {}
            for go in agentic_template["granular_objectives"]:
                comp = go["complexity"]
                complexity_dist[comp] = complexity_dist.get(comp, 0) + 1
            
            print(f"\n⚡ Complexity Distribution:")
            for comp, count in complexity_dist.items():
                percentage = (count / len(agentic_template["granular_objectives"])) * 100
                print(f"  {comp}: {count} ({percentage:.1f}%)")
            
            # Show mastery threshold distribution
            thresholds = [go["mastery_threshold"] for go in agentic_template["granular_objectives"]]
            if thresholds:
                avg_threshold = sum(thresholds) / len(thresholds)
                min_threshold = min(thresholds)
                max_threshold = max(thresholds)
                print(f"\n🎯 Mastery Thresholds:")
                print(f"  Average: {avg_threshold:.3f}")
                print(f"  Range: {min_threshold:.3f} - {max_threshold:.3f}")
            
        except Exception as e:
            print(f"❌ Error exporting template: {e}")
            raise

    def create_sample_ai_prompt(self, agentic_template: Dict[str, Any]) -> str:
        """Create a sample prompt showing how the agentic AI would use this template."""
        
        sample_go = agentic_template["granular_objectives"][0]
        
        sample_prompt = f"""
AGENTIC AI INSTRUCTIONAL PROMPT EXAMPLE:

Context from Template:
- Course: {agentic_template['metadata']['course_code']} - {agentic_template['metadata']['course_name']}
- Learning Objective: {sample_go['parent_lo_id']}
- Granular Objective: {sample_go['go_id']} - {sample_go['skill_display_name']}
- Description: {sample_go['description']}
- Cognitive Level: {sample_go['cognitive_level']} (Level {sample_go['cognitive_level_number']})
- Complexity: {sample_go['complexity']}
- Mastery Threshold: {sample_go['mastery_threshold']:.2f}
- Assessment Strategy: {sample_go['assessment_strategies'][0]['type']}
- Estimated Difficulty: {sample_go['estimated_difficulty']}/5

Tutoring Guidance:
- Primary Focus: {sample_go['tutoring_guidance']['primary_focus']}
- Common Misconceptions: {', '.join(sample_go['tutoring_guidance']['common_misconceptions'])}
- Teaching Strategies: {', '.join(sample_go['tutoring_guidance']['teaching_strategies'])}

AI Agent Instructions:
You are teaching "{sample_go['skill_display_name']}" to a student. Based on the template:
1. Use {sample_go['ai_generation_parameters']['explanation_style']} explanations
2. Provide {sample_go['ai_generation_parameters']['example_complexity']} level examples
3. Assess using {sample_go['assessment_strategies'][0]['type']} methods
4. Maintain mastery threshold of {sample_go['mastery_threshold']:.2f}
5. Consider prerequisite concepts: {', '.join(sample_go.get('prerequisite_concepts', []))}
6. Focus on conceptual tags: {', '.join(sample_go.get('conceptual_tags', []))}
7. Watch for common misconceptions and use appropriate teaching strategies
8. Adapt based on student performance using the defined adaptive rules

This template provides complete context for personalized, adaptive instruction with detailed tutoring guidance.
        """
        
        return sample_prompt.strip()

    def process_complete_conversion(self, xlsx_file_path: str, 
                                  output_filename: str = "agentic_ai_template.json"):
        """
        Main method to convert course objectives XLSX to agentic AI template.
        """
        
        print("🚀 Starting Agentic AI Template Conversion from XLSX")
        print("=" * 60)
        
        # Load the course objectives from XLSX
        course_data = self.load_course_objectives_xlsx(xlsx_file_path)
        
        # Convert to agentic template
        agentic_template = self.convert_to_agentic_template(course_data)
        
        # Export the template
        self.export_template(agentic_template, output_filename)
        
        # Create and display sample prompt
        sample_prompt = self.create_sample_ai_prompt(agentic_template)
        
        print(f"\n🤖 SAMPLE AI AGENT USAGE:")
        print(sample_prompt)
        
        print(f"\n🎉 Conversion Complete!")
        print(f"Your agentic AI template is ready for integration with AI teaching systems.")
        
        return agentic_template


def main():
    """
    Main execution function for creating the KC model JSON files.
    """
    
    # Check command line arguments
    if len(sys.argv) != 2:
        print("Usage: python create_kc_model.py <COURSE_CODE>")
        print("Example: python create_kc_model.py CMP511")
        sys.exit(1)
    
    course_code = sys.argv[1]
    
    # Define file paths
    xlsx_file_path = f"{course_code}_Improved_KC_Model_Updated.xlsx"
    output_file = f"KC_Model_{course_code}.json"
    
    # Check if input file exists
    if not os.path.exists(xlsx_file_path):
        print(f"❌ Error: Input file '{xlsx_file_path}' not found")
        print(f"Expected file: {xlsx_file_path}")
        print(f"\nThis file should be the output from Step 2 after manual editing in Step 3.")
        print(f"Please ensure you have:")
        print(f"1. Completed Step 2: python kc_model_generator.py {course_code}")
        print(f"2. Manually reviewed and edited the generated file")
        print(f"3. Saved the edited file as: {xlsx_file_path}")
        sys.exit(1)
    
    try:
        # Initialize the converter
        converter = AgenticAITemplateConverter()
        
        # Convert XLSX file to agentic AI template
        template = converter.process_complete_conversion(xlsx_file_path, output_file)
        
        print(f"\n🎉 KC Model Creation Complete!")
        print(f"📁 Main JSON file: {output_file}")
        print(f"📁 UI navigation file: {output_file.replace('.json', '_ui_navigation.json')}")
        
        print(f"\n📋 FILES CREATED:")
        print(f"1. {output_file} - Main KC model for LEA environment")
        print(f"2. {output_file.replace('.json', '_ui_navigation.json')} - UI navigation structure")
        
        print(f"\n🚀 DEPLOYMENT READY:")
        print(f"Upload these JSON files to your LEA environment to activate the KC model.")
        
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        print("\n🔧 TROUBLESHOOTING:")
        print("1. Verify the input XLSX file exists and is properly formatted")
        print("2. Check that the file has the expected columns and data structure")
        print("3. Ensure the XLSX file is not open in Excel (close it first)")
        print("4. Install required packages: pip install pandas openpyxl")


if __name__ == "__main__":
    main()