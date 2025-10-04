# File: src/ui/components/icon_manager.py
"""
Icon Manager for LEA UI
Handles avatar generation and icon display
"""

class IconManager:
    """Manages icons and avatars for the LEA interface"""
    
    def __init__(self):
        self.lea_color = "#6c757d"  # Gray for LEA
        self.user_color = "#007bff"  # Blue for users
    
    def get_page_icon(self):
        """Return page icon for Streamlit config"""
        return "🎓"
    
    def get_html_icon(self, size=(32, 32)):
        """Get HTML icon for inline display"""
        return "🎓"
    
    def generate_avatar_svg(self, text: str, bg_color: str, size: int = 40) -> str:
        """
        Generate SVG avatar with text
        
        Args:
            text: Text to display in avatar (usually initials)
            bg_color: Background color hex
            size: Avatar size in pixels
        
        Returns:
            SVG string for avatar
        """
        return f"""
        <svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 100 100'>
            <circle cx='50' cy='50' r='45' fill='{bg_color}'/>
            <text x='50' y='67' font-size='45' text-anchor='middle' fill='white' font-family='Arial, sans-serif' font-weight='600'>
                {text}
            </text>
        </svg>
        """
    
    def get_lea_avatar_html(self, size: int = 40) -> str:
        """Get LEA avatar as HTML img tag"""
        svg = self.generate_avatar_svg("LEA", self.lea_color, size)
        # Convert to data URI
        import base64
        svg_b64 = base64.b64encode(svg.encode()).decode()
        return f'<img src="data:image/svg+xml;base64,{svg_b64}" class="avatar" width="{size}" height="{size}">'
    
    def get_user_avatar_html(self, username: str, size: int = 40) -> str:
        """Get user avatar as HTML img tag"""
        initial = username[0].upper() if username else "U"
        svg = self.generate_avatar_svg(initial, self.user_color, size)
        # Convert to data URI
        import base64
        svg_b64 = base64.b64encode(svg.encode()).decode()
        return f'<img src="data:image/svg+xml;base64,{svg_b64}" class="avatar" width="{size}" height="{size}">'

# Create global instance
icon_manager = IconManager()