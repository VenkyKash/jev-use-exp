"""App-independent, observed AX screen bounds to validated capture pixels."""
import math
from dataclasses import dataclass
from core import Candidate


@dataclass(frozen=True)
class AreaClick(Candidate):
    """One immutable target/area selection, executed as one coordinate click."""
    target_index: int = -1
    area_index: int = -1


def area_clicks(observation, accepts):
    choices = []
    for target in observation.elements:
        actions = {a.removeprefix('AX').lower() for a in target.actions}
        if not target.enabled or not ('press' in actions or target.role in {
                'AXButton', 'AXCheckBox', 'AXRadioButton', 'AXRow', 'AXCell',
                'AXLink', 'AXMenuItem', 'AXPopUpButton', 'AXComboBox', 'AXTab', 'AXImage'}):
            continue
        for area in observation.elements:
            if area.index != target.index:
                if area.parent != target.index or not target.frame or not area.frame:
                    continue
                tx, ty, tw, th = target.frame
                ax, ay, aw, ah = area.frame
                if ax < tx or ay < ty or ax+aw > tx+tw or ay+ah > ty+th:
                    continue
            point = center(area, observation)
            if point is None:
                continue
            for delivery in ('background', 'foreground'):
                args = dict(pid=observation.pid, window_id=observation.window_id,
                            x=point[0], y=point[1], delivery_mode=delivery)
                if target.token:
                    args['element_token'] = target.token
                else:
                    args['element_index'] = target.index
                    args['snapshot_id'] = observation.id
                if accepts('click', args):
                    choices.append(AreaClick(
                        f'click-{target.index}-area-{area.index}-{delivery}',
                        f'Click target {target.index} {target.role} {target.label!r}; '
                        f'area {area.index} {area.role} {area.label!r}, observed center, '
                        f'{delivery} coordinates. One click; a child in this area may receive it.',
                        'click', args, target_index=target.index, area_index=area.index))
    return choices


def numbers(values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def element_frame(raw):
    if not isinstance(raw, dict):
        return None
    values = tuple(raw.get(k) for k in ('x', 'y', 'w', 'h'))
    return values if numbers(values) and values[2] > 0 and values[3] > 0 else None


def capture_geometry(raw):
    if raw.get('screenshot_frame_valid') is not True:
        return None
    bounds = raw.get('window_bounds') or {}
    rect = tuple(bounds.get(k) for k in ('x', 'y', 'width', 'height'))
    dims = (raw.get('screenshot_width'), raw.get('screenshot_height'))
    if not numbers(rect+dims) or min(rect[2:]+dims) <= 0:
        return None
    sx, sy = dims[0]/rect[2], dims[1]/rect[3]
    if not math.isclose(sx, sy, rel_tol=.01):
        return None
    return dict(window_bounds=dict(bounds), width=dims[0], height=dims[1],
                coordinate_space='window-local screenshot pixels')


def center(element, observation):
    geometry, frame = observation.geometry, element.frame
    if not geometry or not frame or not element.enabled:
        return None
    b = geometry['window_bounds']
    x, y, w, h = frame
    # Tiny virtualized/offscreen controls and clipped rectangles are not reliable
    # mouse targets. No widening, clipping into another target, or guessed points.
    if min(w, h) <= 1 or x < b['x'] or y < b['y'] or x+w > b['x']+b['width'] or y+h > b['y']+b['height']:
        return None
    return ((x+w/2-b['x'])*geometry['width']/b['width'],
            (y+h/2-b['y'])*geometry['height']/b['height'])


async def validate_pixel_target(driver, observation):
    from native_errors import DiagnosticError
    if not observation.geometry:
        raise DiagnosticError('missing_click_geometry', 'Coordinate click requires fresh validated capture geometry')
    windows = (await driver.call('list_windows', {'pid': observation.pid})).get('windows', [])
    win = next((w for w in windows if w.get('window_id') == observation.window_id), None)
    if (win is None or win.get('pid') != observation.pid or win.get('is_on_screen') is not True
            or win.get('on_current_space') is False
            or win.get('bounds') != observation.geometry['window_bounds']):
        raise DiagnosticError('stale_click_geometry', 'Window moved, resized or is not visible; reobserve before coordinate input')
