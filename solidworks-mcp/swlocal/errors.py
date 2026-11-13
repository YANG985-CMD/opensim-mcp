"""File-load error bits from the installed/public SOLIDWORKS 2025 API."""
LOAD_ERRORS=(
    (262144,'LOW_RESOURCES','SOLIDWORKS reported low memory or exhausted GDI resources. Stop modelling and release resources; no automatic retry.'),
    (8388608,'APPLICATION_BUSY','SOLIDWORKS is busy and blocked file loading. Inspect the application before trying again.'),
    (1048576,'OPEN_INTERRUPTED','The native file-open operation was interrupted; it was not retried.'),
    (65536,'DOCUMENT_NAME_COLLISION','A different document with the same filename is already loaded. Choose a unique filename or explicitly close the conflicting document.'),
    (4194304,'FILE_CRITICAL_REPAIR_REQUIRED','SOLIDWORKS reported critical document corruption. No repair was attempted.'),
    (2097152,'FILE_REPAIR_REQUIRED','SOLIDWORKS reported non-critical custom-property corruption. This file was not accepted as a verified component, and no repair was attempted.'),
)


def load_error(errors,warnings=0):
    for bit,code,message in LOAD_ERRORS:
        if errors & bit:
            return dict(code=code,message=message,native_errors=errors,native_warnings=warnings,edit_may_be_partial=False,retry_automatically=False)
    return dict(code='OPEN_FAILED',message='Native file loading failed; no automatic retry.',native_errors=errors,native_warnings=warnings,edit_may_be_partial=False,retry_automatically=False)
