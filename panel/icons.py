from __future__ import annotations


def icon(name: str) -> str:
    icons = {
        "add": '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
        "arrow_down": '<svg viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
        "arrow_left": '<svg viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>',
        "arrow_right": '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
        "arrow_up": '<svg viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
        "board": (
            '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="4"/>'
            '<path d="M9 4v16M3 10h18"/></svg>'
        ),
        "card": '<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="4"/><path d="M8 10h8M8 14h5"/></svg>',
        "check": '<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>',
        "close": '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
        "edit": '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
        "grip": (
            '<svg viewBox="0 0 24 24"><circle cx="9" cy="6" r="1.2"/><circle cx="15" cy="6" r="1.2"/>'
            '<circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/>'
            '<circle cx="9" cy="18" r="1.2"/><circle cx="15" cy="18" r="1.2"/></svg>'
        ),
        "file": '<svg viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v6h5"/><path d="M10 14h6M10 18h4"/></svg>',
        "image": '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="4"/><path d="m8 14 2.3-2.3a1 1 0 0 1 1.4 0L16 16"/><circle cx="8" cy="9" r="1.3"/></svg>',
        "link": '<svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"/></svg>',
        "lock": (
            '<svg viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="10" rx="3"/>'
            '<path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>'
        ),
        "stats": '<svg viewBox="0 0 24 24"><path d="M5 19V9M12 19V5M19 19v-7"/></svg>',
        "trash": '<svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15"/></svg>',
        "users": '<svg viewBox="0 0 24 24"><path d="M16 19c0-2.2-1.8-4-4-4H7c-2.2 0-4 1.8-4 4"/><circle cx="9.5" cy="8" r="3"/><path d="M21 19c0-1.8-1.1-3.3-2.8-3.8"/><path d="M16.5 5.3a3 3 0 0 1 0 5.4"/></svg>',
        "view": '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="3"/></svg>',
    }
    return icons.get(name, icons["card"])
