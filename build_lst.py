"""Build one LST report artifact per candidate from a JSON content file.
Usage: python3 build_lst.py content_lst.json outdir
content_lst.json shape:
{ "session": "LST-B",
  "trainer": "B",                      # whose comment boxes these are on the eTags form
  "candidates": {
    "FO": {                            # label: FO, or FO1 / FO2 when two candidates
      "rows": { "2.5.2": {"repeats": 0, "grade": 4, "reason": "HS", "text": ""},
                "3.4.5": {...}, ... },  # one entry per eTags row this candidate was tested on.
                                       # Selectable sections (3.4.x, 3.6.x) show as dropdowns pre-set to the codes
                                       # given here, topped up from the script defaults if fewer than 3.
      "result": "PASS",                # PASS / FAIL / INCOMPLETE
      "trainer": "...",                # Additional Comments from Trainer <x>
      "pams": {"k": {"grade": 4, "text": "..."}, ..., "l": {...}},   # grade 1-5 or "NA"
      "oc": "..." } } }
Row form structure (codes, labels, sections, pick-3 rules) lives in FORMS below. It is form
structure, not session data. No session content lives in this script or the template.
"""
import json, sys, os, time

POOL_34 = [('3.4.0', 'Engine'), ('3.4.1', 'Pressurization and air conditioning'), ('3.4.2', 'Pitot / static system'),
           ('3.4.3', 'Fuel system'), ('3.4.4', 'Electrical system'), ('3.4.5', 'Hydraulic system'),
           ('3.4.6', 'Flight Control and Trim system'), ('3.4.7', 'Anti-icing/de-icing system, glare shield heating'),
           ('3.4.8', 'Autopilot / Flight Director'),
           ('3.4.9', 'Stall warning devices or stall avoidance devices, and stability augmentation devices'),
           ('3.4.10', 'GPWS, Weather radar, radio altimeter, transponder'), ('3.4.11', 'Radios, nav equipment, instruments, FMS'),
           ('3.4.12', 'Landing gear and brake'), ('3.4.13', 'Slat and flap system'), ('3.4.14', 'Auxiliary power unit (APU)')]
POOL_36 = [('3.6.1', 'Fire drills e.g. engine, APU, cabin, cargo compartment, flight deck, wing and electrical fires including evacuation'),
           ('3.6.2', 'Smoke control and removal'), ('3.6.3', 'Engine failures, shutdown and restart at a safe height'),
           ('3.6.4', 'Fuel dumping (simulated)'), ('3.6.5', 'Wind shear at take-off / landing (FS only)'),
           ('3.6.6', 'Simulated cabin pressure failure / Emergency descent'), ('3.6.7', 'Incapacitation of flight crew member'),
           ('3.6.8', 'Other emergency procedures as outlined in the appropriate aeroplane flight manual (AFM)'), ('3.6.9', 'TCAS event')]

# eTags LST form sections per session. "fixed" rows must all be graded; "pick" sections need at least n rows from the pool.
FORMS = {
    'LST-B': [
        {'sec': 'Section 2 - Take offs with simulated engine failure',
         'fixed': [('2.5.2', 'Between V1 and V2 or (FS only)'), ('2.6', 'Rejected take-off at a reasonable speed before reaching V1')]},
        {'sec': 'Section 3 - Normal and abnormal operations of systems (min 3 from 3.4.0-3.4.14)', 'pick': 3, 'pool': POOL_34,
         'default': ['3.4.0', '3.4.5', '3.4.8']},
        {'sec': 'Section 3 - Abnormal and emergency procedures (min 3 from 3.6.1-3.6.9)', 'pick': 3, 'pool': POOL_36,
         'default': ['3.6.1', '3.6.3', '3.6.5', '3.6.9']},
        {'sec': 'Section 3 - Instrument flight procedures',
         'fixed': [('3.8.1', 'Adherence to departure and arrival routes and ATC instructions')]},
        {'sec': 'Section 3 - Precision approaches down to DH not less than 60m (200ft)',
         'fixed': [('3.8.3.1', 'Manually, without flight director'), ('3.8.3.4', 'Manually, with one or two engines inoperative')]},
        {'sec': 'Section 3 - Instrument flight procedures (2D)',
         'fixed': [('3.8.4', '2D operations down to the applicable minima')]},
        {'sec': 'Section 4 - Missed approach procedures',
         'fixed': [('4.4', 'Manual go-around with the critical engine inoperative')]},
        {'sec': 'Section 5 - Landings',
         'fixed': [('5.5', 'Landing with critical engine simulated inoperative')]},
    ],
    # 'LST-C': add when the LST-C eTags form is captured (rows 1.4, 1.6, 3.8.3.3 etc. differ).
}

COMPS = 'khapmsdcl'

# Expected competencies per row (the pad's per-event pre-map), shown dashed on the Reason chips.
EXPECTED = {
    'LST-B': {'2.5.2': 'HSAPM', '2.6': 'PSCM', '3.4.0': 'HSAPM', '3.4.8': 'MHS', '3.6.1': 'PCMSDL', '3.6.3': 'HSAPM',
              '3.6.5': 'PHSC', '3.6.9': 'PH', '3.8.1': 'PCM', '3.8.3.1': 'MHS', '3.8.3.4': 'HS', '3.8.4': 'PA',
              '4.4': 'PH', '5.5': 'H', '_3.4': 'PMSD'},   # _3.4 = any examiner-choice 3.4.x
}


def expected_for(session, code):
    e = EXPECTED.get(session, {})
    if code in e:
        return e[code]
    return e.get('_3.4', '') if code.startswith('3.4.') else ''


def check(text, where):
    bad = [c for c in (text or '') if ord(c) > 126 or (ord(c) < 32 and c != '\n')]
    if bad:
        raise SystemExit(f'non-keyboard characters in {where}: {[hex(ord(c)) for c in bad]}')


def fail(msg):
    raise SystemExit(f'content error: {msg}')


def form_for(session, rows):
    """Return (form, slot_of_code). Locked rows keep their code. Pick-section rows become
    dropdown slots: the codes given in the JSON, topped up from the section defaults to the minimum."""
    if session not in FORMS:
        fail(f'no eTags form defined for {session}')
    known = set()
    out = []
    slot_of = {}
    n = 0
    for s in FORMS[session]:
        if s.get('fixed'):
            known.update(c for c, _ in s['fixed'])
            missing = [c for c, _ in s['fixed'] if c not in rows]
            if missing:
                fail(f'fixed rows missing: {missing}')
            items = []
            for c, l in s['fixed']:
                items.append({'slot': f's{n}', 'code': c, 'label': l, 'expected': expected_for(session, c)}); slot_of[c] = f's{n}'; n += 1
        else:
            pool = s['pool']
            known.update(c for c, _ in pool)
            codes = [c for c, _ in pool if c in rows]
            for c in s.get('default', []):
                if len(codes) >= s['pick']:
                    break
                if c not in codes:
                    codes.append(c)
            if len(codes) < s['pick']:
                fail(f'{s["sec"]}: {len(codes)} rows, minimum {s["pick"]}')
            labels = dict(pool)
            items = []
            for c in codes:
                items.append({'slot': f's{n}', 'code': c, 'label': labels[c], 'pool': [list(x) for x in pool],
                              'expmap': {pc: expected_for(session, pc) for pc, _ in pool}}); slot_of[c] = f's{n}'; n += 1
        sec = {'sec': s['sec'], 'items': items}
        if s.get('pick'):
            sec['pick'] = s['pick']
        out.append(sec)
    unknown = [c for c in rows if c not in known]
    if unknown:
        fail(f'rows not on the {session} form: {unknown}')
    return out, slot_of


def main():
    content = json.load(open(sys.argv[1], encoding='utf-8'))
    outdir = sys.argv[2] if len(sys.argv) > 2 else '.'
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'LST_Template.html'), encoding='utf-8').read()
    session = content['session']
    trainer = content.get('trainer', 'B')
    check(session, 'session'); check(trainer, 'trainer')
    build = time.strftime('%Y%m%d%H%M%S')
    for label, p in content['candidates'].items():
        check(label, 'label')
        rows = p.get('rows', {})
        form, slot_of = form_for(session, rows)
        reps = 0
        clean_rows = {}
        for code, r in rows.items():
            g = r.get('grade')
            if g is not None and g not in (1, 2, 3, 4, 5):
                fail(f'{label} {code}: grade {g!r}')
            rp = int(r.get('repeats', 0))
            if rp not in (0, 1):
                fail(f'{label} {code}: repeats {rp} (one per item)')
            reps += rp
            reason = ''.join(ch for ch in str(r.get('reason', '')).upper() if ch.isalpha())
            if any(ch not in COMPS.upper() for ch in reason):
                fail(f'{label} {code}: reason {reason!r}')
            check(r.get('text', ''), f'{label} {code}')
            clean_rows[slot_of[code]] = {'code': code, 'repeats': rp, 'grade': g, 'reason': reason, 'text': r.get('text', '')}
        result = p.get('result')
        if result not in (None, 'PASS', 'FAIL', 'INCOMPLETE'):
            fail(f'{label}: result {result!r}')
        if reps > 2 and result != 'FAIL':
            fail(f'{label}: {reps} repeats with result {result}, allowance is 2 (a third repeat means FAIL)')
        pams = {}
        for c in COMPS:
            e = p.get('pams', {}).get(c, {})
            g = e.get('grade')
            if g is not None and g not in (1, 2, 3, 4, 5, 'NA'):
                fail(f'{label} PAMS {c}: grade {g!r}')
            check(e.get('text', ''), f'{label} PAMS {c}')
            pams[c] = {'grade': g, 'text': e.get('text', '')}
        check(p.get('trainer', ''), f'{label} trainer comments'); check(p.get('oc', ''), f'{label} OC')
        pilot = {'label': label, 'rows': clean_rows, 'result': result, 'trainer': p.get('trainer', ''), 'pams': pams, 'oc': p.get('oc', '')}
        out = tpl
        for old, new in [("code: 'XXXX',", f"code: '{session}',"), ("trainer: 'B',", f"trainer: '{trainer}',"),
                         ("build: 'XXXX'", f"build: '{build}'"),
                         ('const FORM = null;  // filled by build_lst.py', 'const FORM = ' + json.dumps(form, indent=2, ensure_ascii=True) + ';'),
                         ('const PILOT = null;  // filled by build_lst.py', 'const PILOT = ' + json.dumps(pilot, indent=2, ensure_ascii=True) + ';')]:
            if out.count(old) != 1:
                raise SystemExit(f'template marker not found once: {old}')
            out = out.replace(old, new)
        path = os.path.join(outdir, f'{session}_Report_{label}.html')
        open(path, 'w', encoding='utf-8').write(out)
        rw = {r['code']: len(r['text'].split()) for r in clean_rows.values() if r['text']}
        pw = {c: len(pams[c]['text'].split()) for c in COMPS}
        print(label, path)
        print('  rows', rw, 'repeats', reps, 'result', result)
        print('  PAMS', pw, 'TR', len(pilot['trainer'].split()), 'OC', len(pilot['oc'].split()))


if __name__ == '__main__':
    main()
