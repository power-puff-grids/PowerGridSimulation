# handlers for Comms.subscribe(), the subscription facilitator

import json, logging, threading 
from math import isfinite

log = logging.getLogger(__name__)

# requirements per schema
DEVICE_KEYS = {
        "bus_1": {"voltage_kv"},
        "bus_2": {"voltage_kv"},
        "bus_3": {"voltage_kv"},
        "bus_4": {"voltage_kv"},

        "line_1": {"loading_percent"},
        "line_2": {"loading_percent"},
        "line_3": {"loading_percent"},

        "solar_pv": {"active_power_kw", "voltage_kv"},
        "irrigation_pump": {"active_power_kw", "reactive_power_kvar", "voltage_kv"},
        "battery": {"active_power_kw", "soc_percent", "voltage_kv"}
        }
ENVELOPE_STRINGS = ["schema_version", "run_id", "snapshot_id", "message_id", "timestamp", "device", "scenario"]

def validate_envelope(message) -> list[str]:
#returns list of issues with message, empty = good message no issues
    if not isinstance(message, dict):
        return ["this message is not JSON."]
    errors=[]
    for field in ENVELOPE_STRINGS:
        value = message.get(field)
        if not isinstance(value, str) or value == "":
            errors.append(f"{field} is empty or not a string.")
    if message.get("schema_version") != "1.0":
        errors.append("message is based on outdated/unsupported schema version")
    if isinstance(message.get("timestamp"), str) and not message["timestamp"].endswith("Z"): 
        errors.append("timestamp is not strictly UTC")
    extra = set(message) - set(ENVELOPE_STRINGS) - {"measurements"}
    if extra:
        errors.append(f"unsupported envelope fields: {extra}")
    measurements = message.get("measurements")
    device = message.get("device")
    if not isinstance(measurements, dict):
        errors.append("measurements must be dict")
    elif device not in DEVICE_KEYS:
        errors.append(f"unrecognized/unsupported device: {device}")
    else:
        if set(measurements) != DEVICE_KEYS[device]:
            errors.append(f"measurements for {device} must be {(DEVICE_KEYS[device])}")
        for key, value in measurements.items():
            if isinstance(value, bool) or not isinstance(value, (int,float)) or not isfinite(value):
                errors.append(f"{key} must be a number")
    return errors

class Validated:
    # allows for logging of bad/incomplete/corrupt msgs
    # Validated(filecontainingnormal.jsonl, filecontainingquarantine.jsonl
    def __init__(self, good, quarantine):
        self.good = good
        self.quarantine = quarantine
    def __call__(self, message, meta):
        errors = validate_envelope(message)
        if errors:
            log.warning("quarantined %s: %s", meta.get("delivery_id"), errors)
            self.quarantine(message, meta, errors)
            return
        self.good(message,meta)


class Recorder:
    #does the actual saving of the data to JSON lines file (format: { meta: {****}, message: {***} } ).
    def __init__(self, straight_path, quarantine_path, attack_path=None):
        self.file = open(straight_path, "a", encoding="utf-8");
        self.bad = open(quarantine_path, "a", encoding="utf-8");
        if attack_path:
            self.attack = open(attack_path, "a", encoding="utf-8");
        else:
            self.attack = None
    def __call__(self, message, meta):
        self.file.write(json.dumps({"meta": meta, "message": message}) + "\n")
        self.file.flush()
    def quarantine(self, message, meta, errors):
        self.bad.write(json.dumps({"meta": meta, "message": message, "errors": errors}) + "\n")
        self.bad.flush()
    # this one is a bit weird because AttacksRelay isnt a callback fn
    def log_attack(self, attack_record):
        if self.attack:
            self.attack.write(json.dumps(attack_record) + "\n")
            self.attack.flush()
    def close(self):
        self.file.close()
        self.bad.close()
        if self.attack:
            self.attack.close()
# TO BE USED ONLY FOR ATTACKMSGS
# STRAIGHT PASSTHROUGHS USE H_SEND()
class AttackRelay:
## republish on receival of msg to {outtopic}/{device}
##usage: generate attackmsg and attack record, put them in relay(attackmsg, attackrecord) to send out the alt msg and save record 
    
    def __init__(self, comms, outtopic, recorder):
        self.comms = comms
        self.outtopic = outtopic
        self.recorder = recorder
    def __call__(self, message, meta, attack_record):
        self.recorder.log_attack(attack_record)
        topic = f"{self.outtopic}/{message['device']}"
        self.comms.h_send(topic, message)

#attacks will be a dict of attacks so that we can choose, will probably have to find a way to 
#pass arguments for attack at the command line, maybe press x then prompts for what device you
# want to attack using attack x and then the intensity of the attack assigned to x (which will have
#to figure out which measurement best fits for that kind of attack i suppose and then pass that
# stuff in as a param to the attack fns  
class AttackRouter:
    def __init__(self, comms, outtopic, attack_relay, attacks, quarantine):
        self.comms = comms
        self.outtopic = outtopic
        self.attack_relay = attack_relay
        self.attacks = attacks
        self.quarantine = quarantine
        self.active_attack = None
        self.lock = threading.Lock()
        self.chosen = None
    def grabfn(self, attack_key, device=None, **params):
        attack_fn = self.attacks[attack_key]
        with self.lock:
            self.chosen = (attack_fn, device, dict(params))
    #surefire way to bypass toggle and turn off attack
    def disable(self):
        with self.lock:
            self.chosen = None
    def __call__(self, message, meta):
        with self.lock:
            chosen = self.chosen
        if chosen is None:
            topic = f"{self.outtopic}/{message['device']}"
            self.comms.h_send(topic, message)
            return
        attack_fn, target, params = chosen
        #let other stuff go through 
        if target is not None and message['device'] != target:
            topic = f"{self.outtopic}/{message['device']}"
            self.comms.h_send(topic, message)
            return
        # the attack fn can reject messages, catch em 
        try:
            altered_message, attack_record = attack_fn(message, **params)
        except ValueError as exc:
            self.quarantine(message, meta, [f"Attack rejected message: {exc}"])
            return

        self.attack_relay(altered_message, meta, attack_record)
