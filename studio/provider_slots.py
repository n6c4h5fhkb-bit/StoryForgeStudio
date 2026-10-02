"""One in-process provider/account capacity shared by both workspace clients."""
import threading

capacity = threading.Condition()
active = {}
