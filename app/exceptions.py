class VotingException(Exception):
    """Base exception for voting app"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class InvalidVoteException(VotingException):
    """Raised when vote is invalid"""
    def __init__(self, message: str = "Invalid vote option"):
        super().__init__(message, 400)

class RoundNotFoundException(VotingException):
    """Raised when round is not found"""
    def __init__(self, message: str = "Round not found"):
        super().__init__(message, 404)

class DatabaseException(VotingException):
    """Raised when database operation fails"""
    def __init__(self, message: str = "Database error"):
        super().__init__(message, 500)