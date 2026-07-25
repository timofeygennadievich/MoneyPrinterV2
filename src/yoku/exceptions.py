"""Expected errors raised by the Yoku Video Factory."""


class YokuError(Exception):
    """Base class for user-correctable Yoku errors."""


class InvalidIdentifierError(YokuError):
    """Raised when a catalog identifier is unsafe or malformed."""


class CatalogItemNotFoundError(YokuError):
    """Raised when a requested catalog item does not exist."""


class CatalogValidationError(YokuError):
    """Raised when catalog JSON is malformed or violates its schema."""


class ReviewPackageError(YokuError):
    """Raised when a review package cannot safely be created."""


class AssetValidationError(YokuError):
    """Raised when a media manifest or asset path is unsafe or invalid."""


class StoryboardPackageError(YokuError):
    """Raised when a storyboard package cannot safely be created."""
