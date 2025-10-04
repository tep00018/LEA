"""
KC Model Generator Script (Step 2)

This script takes an Excel template with course structure and learning objectives,
uses OpenAI API to analyze and generate granular knowledge components,
and outputs an enriched Excel file ready for manual review.

Usage:
    python kc_extractor.py <COURSE_CODE>
    
Input:
    - {COURSE_CODE}.xlsx (Excel template with course structure)
    
Output:
    - {COURSE_CODE}_Improved_KC_Model.xlsx (Generated KC model for review)
"""

import os
from dotenv import load_dotenv
from openai import OpenAI
import json
import pandas as pd
import re
import networkx as nx
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import yaml
from pathlib import Path
import hashlib
import ast

# Load environment variables
load_dotenv()


@dataclass
class KnowledgeComponent:
    """
    Enhanced knowledge component that follows the Excel template structure
    for CMP511 KC model development with UI-optimized naming conventions.
    """
    kc_id: str
    module: str
    module_name: str
    week_num: str
    week_name: str
    lo_num: str
    learning_objective_name: str
    go_num: str
    granular_objective_name: str
    cognitive_level: str
    estimated_difficulty: int
    conceptual_tags: List[str]
    likely_cross_week_connections: List[Dict]
    prerequisite_concepts: List[str]
    week_number: int
    lecture_number: str
    mastery_threshold: float
    threshold_rationale: str


class ImprovedKCExtractor:
    """
    Improved Knowledge Component extraction system that focuses on creating
    unique, contextually appropriate granular components that align directly
    with the learning objectives without excessive repetition.
    """
    
    def __init__(self, openai_api_key: str, course_code: str = "CMP511", course_name: str = None):
        """Initialize the improved extractor with OpenAI API access"""
        self.client = OpenAI(api_key=openai_api_key)
        self.course_code = course_code
        self.course_name = course_name if course_name else f"{course_code} Course"
        
        # Track generated granular components to prevent repetition
        self.used_granular_names = set()
        self.lo_granular_mapping = {}
        
        # Cognitive level thresholds based on Bloom's taxonomy
        self.cognitive_thresholds = {
            "Knowledge": 0.65,
            "Comprehension": 0.70,
            "Application": 0.75,
            "Analysis": 0.80,
            "Synthesis": 0.85,
            "Evaluation": 0.90
        }
        
        # Mapping of complexity indicators to difficulty levels
        self.difficulty_indicators = {
            "basic": 1, "simple": 1, "fundamental": 1, "introduction": 1,
            "understand": 2, "explain": 2, "identify": 2, "describe": 2,
            "apply": 3, "implement": 3, "use": 3, "calculate": 3,
            "analyze": 4, "compare": 4, "evaluate": 4, "assess": 4,
            "create": 5, "design": 5, "develop": 5, "synthesize": 5
        }

    def load_excel_template(self, excel_file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load the Excel template to understand the required structure and format."""
        try:
            template_df = pd.read_excel(excel_file_path, sheet_name='Template', engine='openpyxl')
            example_df = pd.read_excel(excel_file_path, sheet_name='Partial_Example', engine='openpyxl')
            
            print(f"Successfully loaded Excel template from {excel_file_path}")
            print(f"Template contains {len(template_df)} weeks")
            print(f"Example shows format for {len(example_df)} KC entries")
            
            return template_df, example_df
            
        except Exception as e:
            print(f"Error loading Excel template: {e}")
            raise

    def extract_learning_objectives_from_template(self, template_df: pd.DataFrame) -> Dict[int, Dict]:
        """Parse the learning objectives from the template into a structured format."""
        week_structure = {}
        
        for _, row in template_df.iterrows():
            week_num = int(row['Week'])
            week_desc = row['Week Description']
            objectives_text = row['Learning Objectives']
            materials_path = row['Supporting Materials']
            
            objectives = []
            if pd.notna(objectives_text):
                obj_lines = re.split(r'\d+\.\s*', str(objectives_text))
                for obj_line in obj_lines[1:]:
                    clean_obj = re.sub(r'\s+', ' ', obj_line.strip())
                    clean_obj = re.sub(r'[\r\n]+', ' ', clean_obj)
                    if clean_obj and len(clean_obj) > 10:
                        objectives.append(clean_obj)
            
            week_structure[week_num] = {
                'week_name': week_desc,
                'objectives': objectives,
                'materials_path': materials_path,
                'week_number': week_num
            }
            
            print(f"Week {week_num} ({week_desc}): {len(objectives)} learning objectives parsed")
        
        return week_structure

    def create_contextual_concept_names(self, objectives: List[str], week_name: str) -> List[str]:
        """Generate short, contextually appropriate concept names for learning objectives."""
        concept_names = []
        
        concept_prompt = f"""
        Create short, specific concept names (max 25 characters each) for these learning objectives 
        from Week: {week_name} in a {self.course_code} course.
        
        Learning Objectives:
        {chr(10).join([f"{i+1}. {obj}" for i, obj in enumerate(objectives)])}
        
        Requirements:
        - Maximum 25 characters per concept name
        - Focus on the SPECIFIC course concepts
        - Make each name unique and descriptive
        - Use technical terms when appropriate
        
        Return as a JSON list: ["concept1", "concept2", ...]
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You create specific, technical concept names for {self.course_name} educational content."},
                    {"role": "user", "content": concept_prompt}
                ],
                temperature=0.2,
                max_tokens=200
            )
            
            response_content = response.choices[0].message.content.strip()
            json_start = response_content.find('[')
            json_end = response_content.rfind(']') + 1
            
            if json_start != -1 and json_end != 0:
                json_content = response_content[json_start:json_end]
                concept_names = json.loads(json_content)
                concept_names = [name[:25] for name in concept_names[:len(objectives)]]
                
                while len(concept_names) < len(objectives):
                    obj_idx = len(concept_names)
                    fallback = self.create_fallback_concept_name(objectives[obj_idx])
                    concept_names.append(fallback)
                    
        except Exception as e:
            print(f"Error creating concept names, using fallbacks: {e}")
            concept_names = [self.create_fallback_concept_name(obj) for obj in objectives]
        
        return concept_names

    def create_fallback_concept_name(self, objective: str) -> str:
        """Create a fallback concept name when AI generation fails."""
        clean_obj = re.sub(r'^(To\s+)?(understand|explain|learn|identify|be\s+able\s+to|be\s+familiar\s+with)\s+', 
                          '', objective, flags=re.IGNORECASE)
        words = clean_obj.split()[:3]
        return ' '.join(words)[:25]

    def extract_specific_granular_components(self, objective: str, concept_name: str, 
                                           week_name: str, week_num: int) -> List[Dict]:
        """Extract granular knowledge components aligned with the learning objective."""
        
        granular_prompt = f"""
        Break down this learning objective into 2-4 unique, granular knowledge components.
        
        CONTEXT:
        Course: {self.course_code} - {self.course_name}
        Week: {week_num} - {week_name}
        Learning Objective: "{objective}"
        Concept Name: "{concept_name}"
        
        REQUIREMENTS:
        - Each component must be DIRECTLY related to the learning objective
        - Focus on SPECIFIC course concepts
        - Make each component unique and assessable
        - Use precise technical terminology
        
        OUTPUT FORMAT (JSON):
        {{
            "granular_components": [
                {{
                    "granular_name": "specific technical skill (max 40 chars)",
                    "description": "precise description",
                    "cognitive_level": "Knowledge|Comprehension|Application|Analysis|Synthesis|Evaluation",
                    "difficulty_estimate": 1-5,
                    "prerequisite_concepts": ["concept1", "concept2"],
                    "assessment_focus": "how this skill would be tested"
                }}
            ]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are an expert in {self.course_name} pedagogy."},
                    {"role": "user", "content": granular_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            response_content = response.choices[0].message.content
            json_start = response_content.find('{')
            json_end = response_content.rfind('}') + 1
            
            if json_start != -1 and json_end != 0:
                json_content = response_content[json_start:json_end]
                granular_data = json.loads(json_content)
                components = granular_data.get("granular_components", [])
                
                unique_components = []
                for comp in components:
                    granular_name = comp.get('granular_name', '')
                    if self.is_unique_granular_component(granular_name, concept_name):
                        self.used_granular_names.add(granular_name.lower())
                        unique_components.append(comp)
                        
                        if concept_name not in self.lo_granular_mapping:
                            self.lo_granular_mapping[concept_name] = []
                        self.lo_granular_mapping[concept_name].append(granular_name)
                
                return unique_components
                
        except Exception as e:
            print(f"Error extracting granular components: {e}")
            
        return self.create_fallback_granular_components(objective, concept_name)

    def is_unique_granular_component(self, granular_name: str, concept_name: str) -> bool:
        """Check if a granular component is sufficiently unique."""
        return granular_name.lower() not in self.used_granular_names

    def create_fallback_granular_components(self, objective: str, concept_name: str) -> List[Dict]:
        """Create fallback granular components when AI generation fails."""
        return [{
            "granular_name": f"{concept_name} Core Concept",
            "description": f"Master the core concepts of {concept_name.lower()}",
            "cognitive_level": "Comprehension",
            "difficulty_estimate": 2,
            "prerequisite_concepts": [],
            "assessment_focus": f"Test mastery of {concept_name.lower()}"
        }]

    def determine_cross_week_connections(self, concept_name: str, granular_name: str, 
                                       week_num: int, all_concepts: Dict) -> List[Dict]:
        """Analyze potential cross-week connections."""
        return []  # Simplified for now

    def calculate_mastery_threshold(self, cognitive_level: str, difficulty: int, week_num: int) -> Tuple[float, str]:
        """Calculate the mastery threshold based on cognitive level and difficulty."""
        base_threshold = self.cognitive_thresholds.get(cognitive_level, 0.70)
        difficulty_adjustment = (difficulty - 3) * 0.05
        week_adjustment = min(0.05, (week_num - 1) * 0.005)
        
        final_threshold = max(0.60, min(0.95, base_threshold + difficulty_adjustment + week_adjustment))
        
        rationale = (f"Base: {base_threshold} ({cognitive_level}) + "
                    f"Difficulty: {difficulty_adjustment:+.2f} + "
                    f"Week: {week_adjustment:+.2f} = {final_threshold:.2f}")
        
        return round(final_threshold, 2), rationale

    def process_week_materials(self, week_data: Dict, all_concepts: Dict) -> List[KnowledgeComponent]:
        """Process all materials and objectives for a single week."""
        week_num = week_data['week_number']
        week_name = week_data['week_name']
        objectives = week_data['objectives']
        
        print(f"\nProcessing Week {week_num}: {week_name}")
        
        concept_names = self.create_contextual_concept_names(objectives, week_name)
        
        all_concepts[week_num] = {
            'concept_names': concept_names,
            'week_name': week_name
        }
        
        knowledge_components = []
        
        for lo_idx, (objective, concept_name) in enumerate(zip(objectives, concept_names), 1):
            print(f"  Processing LO{lo_idx:02d}: {concept_name}")
            
            granular_components = self.extract_specific_granular_components(
                objective, concept_name, week_name, week_num
            )
            
            if not granular_components:
                granular_components = self.create_fallback_granular_components(objective, concept_name)
            
            for go_idx, granular in enumerate(granular_components, 1):
                connections = self.determine_cross_week_connections(
                    concept_name, granular['granular_name'], week_num, all_concepts
                )
                
                cognitive_level = granular.get('cognitive_level', 'Comprehension')
                difficulty = granular.get('difficulty_estimate', 2)
                threshold, rationale = self.calculate_mastery_threshold(cognitive_level, difficulty, week_num)
                
                kc = KnowledgeComponent(
                    kc_id=f"KC_W{week_num:02d}_L{lo_idx:02d}_{go_idx:03d}",
                    module=self.course_code,
                    module_name=self.course_name,
                    week_num=f"W{week_num:02d}",
                    week_name=week_name,
                    lo_num=f"L{lo_idx:02d}",
                    learning_objective_name=concept_name,
                    go_num=f"{go_idx:03d}",
                    granular_objective_name=granular['granular_name'],
                    cognitive_level=cognitive_level,
                    estimated_difficulty=difficulty,
                    conceptual_tags=[concept_name.lower().replace(' ', '_')] + 
                                  granular.get('prerequisite_concepts', [])[:2],
                    likely_cross_week_connections=connections,
                    prerequisite_concepts=granular.get('prerequisite_concepts', []),
                    week_number=week_num,
                    lecture_number=chr(64 + lo_idx),
                    mastery_threshold=threshold,
                    threshold_rationale=rationale
                )
                
                knowledge_components.append(kc)
        
        print(f"Week {week_num} complete: {len(knowledge_components)} knowledge components created")
        return knowledge_components

    def export_to_excel_template(self, all_kcs: List[KnowledgeComponent], 
                                output_filename: str, example_df: pd.DataFrame):
        """Export the knowledge components to Excel."""
        print(f"\nExporting {len(all_kcs)} knowledge components to Excel...")
        
        export_data = []
        
        for kc in all_kcs:
            row_data = {
                'KC#': kc.kc_id,
                'Module': kc.module,
                'Module Name': kc.module_name,
                'Week #': kc.week_num,
                'Week Name': kc.week_name,
                'LO#': kc.lo_num,
                'Learning Objective Name': kc.learning_objective_name,
                'GO#': kc.go_num,
                'Granular Objective Name': kc.granular_objective_name,
                'cognitive_level': kc.cognitive_level,
                'estimated_difficulty': kc.estimated_difficulty,
                'conceptual_tags': str(kc.conceptual_tags),
                'likely_cross_week_connections': str(kc.likely_cross_week_connections),
                'prerequisite_concepts': str(kc.prerequisite_concepts),
                'week_number': kc.week_number,
                'lecture_number': kc.lecture_number,
                'mastery_threshold': kc.mastery_threshold,
                'threshold_rationale': kc.threshold_rationale
            }
            export_data.append(row_data)
        
        kc_df = pd.DataFrame(export_data)
        
        if not example_df.empty:
            kc_df = kc_df.reindex(columns=example_df.columns, fill_value='')
        
        try:
            with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
                kc_df.to_excel(writer, sheet_name='Complete_KC_Model', index=False)
        except ImportError:
            with pd.ExcelWriter(output_filename) as writer:
                kc_df.to_excel(writer, sheet_name='Complete_KC_Model', index=False)
        
        print(f"Export complete: {output_filename}")
        print(f"\nKC MODEL SUMMARY:")
        print(f"Total Knowledge Components: {len(all_kcs)}")
        print(f"Unique Granular Objectives: {len(set(kc.granular_objective_name for kc in all_kcs))}")

    def process_complete_course(self, excel_template_path: str, output_filename: str):
        """Main method to process the complete course."""
        print("Starting Course KC Extraction")
        
        self.used_granular_names = set()
        self.lo_granular_mapping = {}
        
        template_df, example_df = self.load_excel_template(excel_template_path)
        week_structure = self.extract_learning_objectives_from_template(template_df)
        
        all_kcs = []
        all_concepts = {}
        
        for week_num, week_data in week_structure.items():
            if week_data['objectives']:
                week_kcs = self.process_week_materials(week_data, all_concepts)
                all_kcs.extend(week_kcs)
        
        self.export_to_excel_template(all_kcs, output_filename, example_df)
        
        return all_kcs, week_structure


def main():
    """Main execution function."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python kc_model_generator.py <COURSE_CODE>")
        print("Example: python kc_model_generator.py DEMO101")
        sys.exit(1)
    
    course_code = sys.argv[1]
    
    course_names = {
        "CMP511": "Machine Learning and Artificial Intelligence",
        "PSY555": "Psychology",
        "DEMO101": "Introduction to AI/ML",
    }
    
    course_name = course_names.get(course_code, f"{course_code} Course")
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment variables")
        return
    
    try:
        extractor = ImprovedKCExtractor(api_key, course_code, course_name)
        
        excel_template_path = f"{course_code}.xlsx"
        output_filename = f"{course_code}_Improved_KC_Model.xlsx"
        
        print(f"Processing course: {course_code} - {course_name}")
        print(f"Looking for template: {excel_template_path}")
        
        knowledge_components, week_structure = extractor.process_complete_course(
            excel_template_path, output_filename
        )
        
        print(f"\nKC Model Generation Complete!")
        print(f"Generated {len(knowledge_components)} knowledge components")
        print(f"Output saved to: {output_filename}")
        
    except FileNotFoundError as e:
        print(f"Error: Template file not found - {e}")
    except Exception as e:
        print(f"Error in KC extraction: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
