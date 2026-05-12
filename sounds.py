"""
Generación procedural de música y efectos de sonido para Vertex Valley.
No requiere archivos de audio externos — todo se genera con numpy.
"""
import io
import math
import wave

try:
    import numpy as np
    _OK = True
except ImportError:
    _OK = False

import pygame

SR = 22050   # sample rate


def _available() -> bool:
    return _OK and pygame.mixer.get_init() is not None


def _env(n: int, attack=0.01, release=0.06) -> "np.ndarray":
    e = np.ones(n)
    a = min(n, int(SR * attack))
    r = min(n, int(SR * release))
    if a: e[:a]  = np.linspace(0, 1, a)
    if r: e[-r:] = np.linspace(1, 0, r)
    return e


def _wave(kind: str, freq: float, n: int) -> "np.ndarray":
    t = np.arange(n) / SR
    if kind == 'sine':     return np.sin(2*math.pi*freq*t)
    if kind == 'square':   return np.sign(np.sin(2*math.pi*freq*t))
    if kind == 'triangle': return 2*np.abs(2*(t*freq - np.floor(t*freq+.5)))-1
    if kind == 'saw':      return 2*(t*freq - np.floor(t*freq+.5))
    return np.sin(2*math.pi*freq*t)


def _tone(freq, dur, vol=0.25, kind='square', attack=0.008, release=0.05):
    n = int(SR*dur)
    return _wave(kind, freq, n) * _env(n, attack, release) * vol


def _silence(dur):
    return np.zeros(int(SR*dur))


def _make_sound(arr) -> pygame.mixer.Sound:
    pcm    = np.clip(arr, -1, 1)
    stereo = np.column_stack([pcm, pcm])
    data   = (stereo * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(data)


def _wav_bytes(arr) -> io.BytesIO:
    """Convertir array float a bytes WAV para pygame.mixer.music."""
    buf    = io.BytesIO()
    stereo = np.column_stack([arr, arr])
    pcm    = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    return buf


# ── Frecuencias de notas ───────────────────────────────────────────────────────

N = {
    'C3': 130.81, 'D3': 146.83, 'Eb3':155.56, 'E3': 164.81, 'F3': 174.61,
    'G3': 196.00, 'Ab3':207.65, 'A3': 220.00, 'Bb3':233.08, 'B3': 246.94,
    'C4': 261.63, 'Db4':277.18, 'D4': 293.66, 'Eb4':311.13, 'E4': 329.63,
    'F4': 349.23, 'Gb4':369.99, 'G4': 392.00, 'Ab4':415.30, 'A4': 440.00,
    'Bb4':466.16, 'B4': 493.88, 'C5': 523.25, 'D5': 587.33,
    'E5': 659.25, 'G5': 784.00,
}


# ── Temas musicales ────────────────────────────────────────────────────────────

def make_village_theme() -> io.BytesIO:
    """Melodía alegre en Do mayor — tema de aldea."""
    bpm  = 126
    beat = 60 / bpm
    q, h, e = beat/2, beat, beat/4

    melody = [
        ('E4',q),('G4',e),('C5',h), ('B4',q),('G4',q),
        ('A4',q),('C5',e),('E5',h), ('D5',q),('B4',q),
        ('G4',q),('E4',e),('C4',h), ('D4',q),('F4',q),
        ('G4',h+q),         ('E4',q),('C4',h+q),
    ]
    bass = [
        ('C3',h),('G3',h), ('A3',h),('E3',h),
        ('F3',h),('C3',h), ('G3',h),('C3',h),
    ]

    mel = np.concatenate(
        [np.concatenate([_tone(N[n],d,0.20,'square',0.005,0.04),_silence(0.01)])
         for n,d in melody])
    bas = np.concatenate(
        [_tone(N[n],d,0.12,'triangle',0.01,0.06) for n,d in bass])

    L = max(len(mel), len(bas))
    mel = np.pad(mel,(0,L-len(mel))); bas = np.pad(bas,(0,L-len(bas)))
    return _wav_bytes(mel + bas)


def make_dungeon_theme() -> io.BytesIO:
    """Melodía oscura en La menor — tema de corredor/cueva."""
    bpm  = 100
    beat = 60 / bpm
    q, h = beat/2, beat

    melody = [
        ('A3',q),('C4',q),('E4',q),('A3',h),
        ('G3',q),('Bb3',q),('D4',q),('G3',h),
        ('F3',q),('A3',q), ('C4',q),('F3',h),
        ('E3',q),('G3',q), ('B3',q),('E3',h+q),
    ]
    drone_dur = sum(d for _,d in melody) + len(melody)*0.005
    drone = _tone(55, drone_dur, 0.10, 'sine', 0.1, 0.2)   # A1 drone

    mel = np.concatenate(
        [np.concatenate([_tone(N[n],d,0.17,'square',0.005,0.05),_silence(0.005)])
         for n,d in melody])
    L = max(len(mel), len(drone))
    mel = np.pad(mel,(0,L-len(mel))); drone = np.pad(drone,(0,L-len(drone)))
    return _wav_bytes(mel + drone)


def make_danger_theme() -> io.BytesIO:
    """
    Música de peligro — monstruo cerca.
    Tempo muy rápido, notas disonantes, batido pulsante.
    """
    bpm  = 165
    beat = 60 / bpm
    e, q, s = beat/4, beat/2, beat/8   # corchea, negra, semicorchea

    # Melodía agresiva con tritonos y cromatismos — suena amenazante
    melody = [
        ('A3',s),('A3',s),('Eb4',e),('A3',s),('A3',s),('D4',e),
        ('G3',s),('G3',s),('Db4',e),('G3',s),('Ab3',s),('G3',e),
        ('A3',s),('A3',s),('Eb4',e),('F4', s),('Eb4',s),('D4',e),
        ('E3',e),('Bb3',e),('A3',q+e),
    ]

    # Pulso grave cada beat (onda cuadrada muy baja — como un corazón)
    total_dur = sum(d for _, d in melody) + len(melody)*0.003
    n_pulse   = int(SR * total_dur)
    t_arr     = np.arange(n_pulse) / SR
    pulse_freq= bpm / 60              # un golpe por beat
    pulse     = (np.sign(np.sin(2*np.pi*pulse_freq*t_arr*0.5)) + 1) / 2
    pulse     = pulse * 0.14 * _env(n_pulse, 0.02, 0.02)
    bass_note = _tone(55, total_dur, 0.10, 'sine', 0.05, 0.1)   # A1 drone agresivo

    # Trémolo en melodía (rápido vibrato)
    mel_parts = []
    for n, d in melody:
        tn = int(SR * d)
        ta = np.arange(tn) / SR
        tremolo = 1.0 + 0.3 * np.sin(2*np.pi*14*ta)   # 14 Hz — muy nervioso
        seg = _tone(N[n], d, 0.18, 'square', 0.003, 0.03) * tremolo
        mel_parts.append(seg)
        mel_parts.append(_silence(0.003))

    mel = np.concatenate(mel_parts)
    L   = max(len(mel), len(pulse), len(bass_note))
    mel       = np.pad(mel,       (0, L-len(mel)))
    pulse     = np.pad(pulse,     (0, L-len(pulse)))
    bass_note = np.pad(bass_note, (0, L-len(bass_note)))

    return _wav_bytes(np.clip(mel + pulse + bass_note, -1, 1))


# ── Efectos de sonido ──────────────────────────────────────────────────────────

def make_footstep() -> pygame.mixer.Sound:
    """Suave paso sobre hierba."""
    n   = int(SR*0.07)
    rng = np.random.default_rng(42)
    noise = rng.uniform(-1,1,n) * np.exp(-np.linspace(0,9,n)) * 0.22
    return _make_sound(noise)


def make_hit_enemy() -> pygame.mixer.Sound:
    sig = _tone(180, 0.09, 0.45, 'square', 0.001, 0.04)
    sig += _tone(130, 0.09, 0.20, 'sine',   0.001, 0.05)
    return _make_sound(sig)


def make_hit_player() -> pygame.mixer.Sound:
    sig = _tone(110, 0.13, 0.48, 'square', 0.001, 0.07)
    sig += _tone(75,  0.13, 0.22, 'sine',   0.001, 0.09)
    return _make_sound(sig)


def make_chest_open() -> pygame.mixer.Sound:
    notes = [('C4',0.09),('E4',0.09),('G4',0.09),('C5',0.22)]
    return _make_sound(np.concatenate(
        [_tone(N[n],d,0.30,'triangle',0.005,0.02) for n,d in notes]))


def make_levelup() -> pygame.mixer.Sound:
    notes = [('C4',0.08),('E4',0.08),('G4',0.08),('C5',0.14),('E5',0.32)]
    return _make_sound(np.concatenate(
        [_tone(N[n],d,0.32,'square',0.005,0.02) for n,d in notes]))


def make_shop_bell() -> pygame.mixer.Sound:
    dur = 0.22   # misma duración para poder sumar
    t1  = _tone(880,  dur, 0.28, 'sine', 0.002, 0.12)
    t2  = _tone(1318, dur, 0.18, 'sine', 0.002, 0.10)
    return _make_sound(t1 + t2)


# ── Inicialización ─────────────────────────────────────────────────────────────

def init():
    """Inicializar pygame.mixer y generar todos los sonidos. Retorna SoundBank o None."""
    if not _OK:
        print("[Audio] numpy no disponible — sin sonido.")
        return None
    try:
        pygame.mixer.init(frequency=SR, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(10)
        bank = {
            'footstep':   make_footstep(),
            'hit_enemy':  make_hit_enemy(),
            'hit_player': make_hit_player(),
            'chest':      make_chest_open(),
            'levelup':    make_levelup(),
            'shop_bell':  make_shop_bell(),
        }
        bank['footstep'].set_volume(0.35)
        bank['hit_enemy'].set_volume(0.7)
        bank['hit_player'].set_volume(0.8)
        # Music WAV buffers (loaded on demand)
        bank['_music'] = {
            'village': make_village_theme(),
            'dungeon': make_dungeon_theme(),
            'danger':  make_danger_theme(),
        }
        return bank
    except Exception as ex:
        print(f"[Audio] Error al inicializar: {ex}")
        return None
