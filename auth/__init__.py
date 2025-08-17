# This module only handles JWT validation for Cognito tokens
# Frontend handles all user registration, login, and token management
from .cognito_jwt import get_current_user, get_current_user_optional

# No router needed - frontend handles auth flows directly