// 体积估算面板脚本（交互式模型页共用）
//
// 原先这段脚本由 handlers/processors.py 以 f-string 逐页拼进 HTML，现改为独立文件。
// 页面通过内联的 window.VOL_PANEL_CFG 传入参数：zMin / zMax（网格 Z 数据范围）。
// 网格数据本身仍由页面内嵌的 <script id="geobody-grid-data"> 提供（逐页不同，属于数据）。

(function(){
  "use strict";

  // ===== 常量 & DOM 引用 =====
  var gd = document.getElementById('layer-explode-model');
  if (!gd) gd = document.querySelector('.js-plotly-plot');
  if (!gd) return;

  var gridScript = document.getElementById('geobody-grid-data');
  if (!gridScript) return;
  var gridData = JSON.parse(gridScript.textContent);

  var dg = gridData;
  var xDataMin = dg.x_range[0], xDataMax = dg.x_range[1];
  var yDataMin = dg.y_range[0], yDataMax = dg.y_range[1];
  // 参数由页面内联的 window.VOL_PANEL_CFG 传入（网格 Z 数据范围）
  var _cfg = window.VOL_PANEL_CFG || {};
  var zDataMin = _cfg.zMin, zDataMax = _cfg.zMax;

  // ===== 状态 =====
  var active = false;
  var currentBounds = null;
  var activeLiths = gridData.liths.slice();
  var selectTraces = [];
  var panelCollapsed = false;
  // 框体去重：记录上一次真正画进场景的边界，避免重复的 restyle（每次都会全场景重建）
  var lastBoxKey = null;
  var _boxTimer = null;
  var BOX_DEBOUNCE_MS = 120;

  // 框体三个方向的旋转角（度）：绕 X / 绕 Y / 绕 Z，均绕框体中心旋转
  function getRotAngles() {
    return {
      x: parseFloat(rotXAngle.value) || 0,
      y: parseFloat(rotYAngle.value) || 0,
      z: parseFloat(rotAngle.value) || 0
    };
  }

  // 三个旋转角归零（打开/关闭面板时调用）
  function resetRotation() {
    rotXAngle.value = 0; rotXLabel.textContent = '0°';
    rotYAngle.value = 0; rotYLabel.textContent = '0°';
    rotAngle.value = 0; rotLabel.textContent = '0°';
  }

  function boundsKey(b) {
    var r = getRotAngles();
    return b.xMin + '|' + b.xMax + '|' + b.yMin + '|' + b.yMax + '|' + b.zMin + '|' + b.zMax
      + '|' + r.x + '|' + r.y + '|' + r.z;
  }

  // DOM refs
  var panel = document.getElementById('volume-estimate-panel');
  var btnActivate = document.getElementById('vol-btn-activate');
  if (!btnActivate) return;
  var panelBody = document.getElementById('vol-panel-body');
  var panelToggleBtn = document.getElementById('vol-panel-toggle');
  var panelHeaderBtn = document.getElementById('vol-panel-header-btn');
  var btnCancel = document.getElementById('vol-btn-cancel');
  var btnConfirm = document.getElementById('vol-btn-confirm');
  var resultDiv = document.getElementById('vol-result');
  var lithChecks = document.getElementById('vol-lith-checks');
  var rotAngle = document.getElementById('vol-rot-angle');
  var rotLabel = document.getElementById('vol-rot-label');
  var rotXAngle = document.getElementById('vol-rot-x');
  var rotXLabel = document.getElementById('vol-rot-x-label');
  var rotYAngle = document.getElementById('vol-rot-y');
  var rotYLabel = document.getElementById('vol-rot-y-label');

  var slXMin = document.getElementById('vol-x-min');
  var slXMax = document.getElementById('vol-x-max');
  var slYMin = document.getElementById('vol-y-min');
  var slYMax = document.getElementById('vol-y-max');
  var slZMin = document.getElementById('vol-z-min');
  var slZMax = document.getElementById('vol-z-max');
  var labelX = document.getElementById('vol-x-label');
  var labelY = document.getElementById('vol-y-label');
  var labelZ = document.getElementById('vol-z-label');

  // ===== 初始化岩性复选框 =====
  function buildLithCheckboxes() {
    if (dg.liths.length <= 1) {
      lithChecks.style.display = 'none';
      return;
    }
    var html = '';
    dg.liths.forEach(function(lith) {
      var c = dg.colors[lith] || '#aaa';
      html += '<label><input type="checkbox" class="vol-lith-cb" value="' + lith + '" checked>'
        + '<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' + c + ';"></span> '
        + lith + '</label>';
    });
    lithChecks.innerHTML = html;

    // 绑定复选框事件
    lithChecks.querySelectorAll('.vol-lith-cb').forEach(function(cb) {
      cb.addEventListener('change', function() {
        activeLiths = [];
        lithChecks.querySelectorAll('.vol-lith-cb:checked').forEach(function(c) {
          activeLiths.push(c.value);
        });
        // 选择框不随岩性变化，只需重算读数，无需重绘 3D 场景
        if (active) updateReadout();
      });
    });
  }
  buildLithCheckboxes();

  // ===== 滑块设置 =====
  var SLIDER_STEPS = 1000;

  function sliderToReal(sl, dataMin, dataMax) {
    return dataMin + (parseFloat(sl.value) / SLIDER_STEPS) * (dataMax - dataMin);
  }

  function realToSlider(val, dataMin, dataMax) {
    return Math.round(((val - dataMin) / (dataMax - dataMin)) * SLIDER_STEPS);
  }

  function initSliders() {
    slXMin.max = SLIDER_STEPS; slXMin.value = 0;
    slXMax.max = SLIDER_STEPS; slXMax.value = SLIDER_STEPS;
    slYMin.max = SLIDER_STEPS; slYMin.value = 0;
    slYMax.max = SLIDER_STEPS; slYMax.value = SLIDER_STEPS;
    slZMin.max = SLIDER_STEPS; slZMin.value = 0;
    slZMax.max = SLIDER_STEPS; slZMax.value = SLIDER_STEPS;
  }

  function getBoundsFromSliders() {
    return {
      xMin: sliderToReal(slXMin, xDataMin, xDataMax),
      xMax: sliderToReal(slXMax, xDataMin, xDataMax),
      yMin: sliderToReal(slYMin, yDataMin, yDataMax),
      yMax: sliderToReal(slYMax, yDataMin, yDataMax),
      zMin: sliderToReal(slZMin, zDataMin, zDataMax),
      zMax: sliderToReal(slZMax, zDataMin, zDataMax)
    };
  }

  function setSlidersFromBounds(b) {
    slXMin.value = realToSlider(b.xMin, xDataMin, xDataMax);
    slXMax.value = realToSlider(b.xMax, xDataMin, xDataMax);
    slYMin.value = realToSlider(b.yMin, yDataMin, yDataMax);
    slYMax.value = realToSlider(b.yMax, yDataMin, yDataMax);
    slZMin.value = realToSlider(b.zMin, zDataMin, zDataMax);
    slZMax.value = realToSlider(b.zMax, zDataMin, zDataMax);
  }

  // ===== 体积计算 =====
  function formatVolume(v) {
    if (!v || isNaN(v) || !isFinite(v)) return '0 m³';
    if (v >= 1e9) return (v / 1e9).toFixed(2) + ' km³';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + ' 百万 m³';
    if (v >= 1e4) return Math.round(v).toLocaleString() + ' m³';
    return v.toFixed(1) + ' m³';
  }

  function computeVolume(bounds) {
    var totalVolume = 0, validCells = 0, totalCells = 0, byLith = {};
    var bXMin = Math.min(bounds.xMin, bounds.xMax), bXMax = Math.max(bounds.xMin, bounds.xMax);
    var bYMin = Math.min(bounds.yMin, bounds.yMax), bYMax = Math.max(bounds.yMin, bounds.yMax);
    var bZMin = Math.min(bounds.zMin, bounds.zMax), bZMax = Math.max(bounds.zMin, bounds.zMax);
    // 旋转：把网格点逆变换回框体局部坐标系，再做轴对齐的包含判断。
    // 这里必须是 buildBoxTraces→rotateCorners 的严格逆运算（顺序相反、角度取负）。
    var rot = getRotAngles();
    var useRot = (rot.x !== 0 || rot.y !== 0 || rot.z !== 0);
    var useTilt = (rot.x !== 0 || rot.y !== 0);   // 仅绕 Z 时沿用原二维判定，结果与改动前完全一致
    var cx = (bXMin + bXMax) / 2, cy = (bYMin + bYMax) / 2, cz = (bZMin + bZMax) / 2;
    var hX = (bXMax - bXMin) / 2, hY = (bYMax - bYMin) / 2, hZ = (bZMax - bZMin) / 2;
    // 逆旋转的余弦/正弦（仅绕 Z 时只用得到 cosZ/sinZ）
    var cosX = 1, sinX = 0, cosY = 1, sinY = 0, cosZ = 1, sinZ = 0;
    var inv = null, bX0 = 0, bY0 = 0, bZ0 = 1;
    if (useRot) {
      var rz = -rot.z * Math.PI / 180, ry = -rot.y * Math.PI / 180, rx = -rot.x * Math.PI / 180;
      if (!useTilt) {
        cosZ = Math.cos(rz); sinZ = Math.sin(rz);
      } else {
        cosZ = Math.cos(rz); sinZ = Math.sin(rz);
        cosY = Math.cos(ry); sinY = Math.sin(ry);
        cosX = Math.cos(rx); sinX = Math.sin(rx);
        // 逆变换 = 先逆 Z，再逆 Y，最后逆 X（与正向的 X→Y→Z 互逆）
        inv = function(px, py, pz) {
          var x1 = px * cosZ - py * sinZ, y1 = px * sinZ + py * cosZ, z1 = pz;
          var x2 = x1 * cosY + z1 * sinY, z2 = -x1 * sinY + z1 * cosY, y2 = y1;
          var y3 = y2 * cosX - z2 * sinX, z3 = y2 * sinX + z2 * cosX;
          return [x2, y3, z3];
        };
        // B = 逆旋转对世界 Z 单位向量的像：竖直直线在局部坐标系里是 A + z*B
        var unit = inv(0, 0, 1);
        bX0 = unit[0]; bY0 = unit[1]; bZ0 = unit[2];
      }
    }

    // 板法：用一条轴约束把竖直直线的 z 可达区间收窄到 [st.lo, st.hi]；
    // 返回 false 表示该列与框体无交集。b≈0 表示这条轴与竖直方向平行。
    function clipPlane(a, b, h, st) {
      if (b > 1e-12) {
        var lo = (-h - a) / b, hi = (h - a) / b;
        if (lo > st.lo) st.lo = lo;
        if (hi < st.hi) st.hi = hi;
      } else if (b < -1e-12) {
        var lo = (-h - a) / b, hi = (h - a) / b;   // b<0 时 lo>hi，故上下界互换
        if (hi > st.lo) st.lo = hi;
        if (lo < st.hi) st.hi = lo;
      } else if (a < -h || a > h) {
        return false;
      }
      return st.lo <= st.hi;
    }

    activeLiths.forEach(function(lith) {
      var zd = dg.z_data[lith];
      if (!zd || !zd.z_top || !zd.z_bot) return;
      var lithVol = 0, lithValid = 0;

      for (var i = 0; i < dg.ny; i++) {
        var y = dg.y_range[0] + i * dg.dy;
        for (var j = 0; j < dg.nx; j++) {
          var x = dg.x_range[0] + j * dg.dx;
          var zLo = bZMin, zHi = bZMax;
          if (useTilt) {
            // 含 X/Y 倾斜：把该列的竖直直线逆变换到框体局部坐标系（L = A + z*B），
            // 再逐轴用板法求出 z 的可行区间，等价于「竖直线与旋转后的框体求交」。
            var A = inv(x - cx, y - cy, -cz);
            // 注意：初始区间必须是 ±∞，不能预夹到 [bZMin, bZMax]——
            // 倾斜后的框体在某一列的竖直跨度可以超出它原来的高程范围。
            var st = { lo: -Infinity, hi: Infinity };
            if (!clipPlane(A[0], bX0, hX, st)) continue;
            if (!clipPlane(A[1], bY0, hY, st)) continue;
            if (!clipPlane(A[2], bZ0, hZ, st)) continue;
            zLo = st.lo; zHi = st.hi;
          } else if (useRot) {
            // 仅绕 Z 旋转：与原实现完全一致的二维逆旋转判定
            var ddx = x - cx, ddy = y - cy;
            var wx = cx + ddx * cosZ - ddy * sinZ;
            var wy = cy + ddx * sinZ + ddy * cosZ;
            if (wx < bXMin || wx > bXMax || wy < bYMin || wy > bYMax) continue;
          } else {
            if (x < bXMin || x > bXMax || y < bYMin || y > bYMax) continue;
          }

          var zt = zd.z_top[i][j];
          var zb = zd.z_bot[i][j];
          if (zt === null || zb === null) continue;
          totalCells++;

          var topClip = Math.min(zt, zHi), botClip = Math.max(zb, zLo);
          if (topClip <= botClip) continue;
          lithVol += dg.dx * dg.dy * (topClip - botClip);
          lithValid++;
        }
      }

      byLith[lith] = lithVol;
      totalVolume += lithVol;
      validCells += lithValid;
    });

    return {
      total: totalVolume,
      byLith: byLith,
      validCells: validCells,
      totalCells: totalCells,
      cellArea: dg.dx * dg.dy
    };
  }

  // ===== 选择框渲染（支持绕 X / Y / Z 三轴旋转） =====
  // 依次绕 X、绕 Y、绕 Z 旋转，全部绕框体中心；三轴为 0 时原样返回。
  // 与 computeVolume 里的逆变换必须严格互为逆运算，否则读数与框体不一致。
  function rotateCorners(corners, rx, ry, rz) {
    if (!rx && !ry && !rz) return corners;
    var radX = rx * Math.PI / 180, radY = ry * Math.PI / 180, radZ = rz * Math.PI / 180;
    var cX = Math.cos(radX), sX = Math.sin(radX);
    var cY = Math.cos(radY), sY = Math.sin(radY);
    var cZ = Math.cos(radZ), sZ = Math.sin(radZ);
    var cx = 0, cy = 0, cz = 0, n = corners.length;
    for (var i = 0; i < n; i++) { cx += corners[i][0]; cy += corners[i][1]; cz += corners[i][2]; }
    cx /= n; cy /= n; cz /= n;
    return corners.map(function(v) {
      var x = v[0] - cx, y = v[1] - cy, z = v[2] - cz;
      // 绕 X 轴
      var y1 = y * cX - z * sX, z1 = y * sX + z * cX;
      // 绕 Y 轴
      var x2 = x * cY + z1 * sY, z2 = -x * sY + z1 * cY;
      // 绕 Z 轴（与原实现一致）
      var x3 = x2 * cZ - y1 * sZ, y3 = x2 * sZ + y1 * cZ;
      return [cx + x3, cy + y3, cz + z2];
    });
  }

  function buildBoxTraces(bounds) {
    var bXMin = Math.min(bounds.xMin, bounds.xMax), bXMax = Math.max(bounds.xMin, bounds.xMax);
    var bYMin = Math.min(bounds.yMin, bounds.yMax), bYMax = Math.max(bounds.yMin, bounds.yMax);
    var bZMin = Math.min(bounds.zMin, bounds.zMax), bZMax = Math.max(bounds.zMin, bounds.zMax);
    var rot = getRotAngles();
    var c = rotateCorners([[bXMin,bYMin,bZMin],[bXMax,bYMin,bZMin],[bXMax,bYMax,bZMin],[bXMin,bYMax,bZMin],
                           [bXMin,bYMin,bZMax],[bXMax,bYMin,bZMax],[bXMax,bYMax,bZMax],[bXMin,bYMax,bZMax]],
                          rot.x, rot.y, rot.z);
    var meshI = [0,0, 4,4, 0,0, 2,2, 0,0, 1,1];
    var meshJ = [1,2, 5,6, 1,5, 3,7, 3,7, 2,6];
    var meshK = [2,3, 6,7, 5,4, 7,6, 7,4, 6,5];
    var faceColor = 'rgba(0,229,255,0.10)', edgeColor = 'rgba(0,229,255,0.75)';
    var edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
    var ex = [], ey = [], ez = [];
    edges.forEach(function(e) { ex.push(null, c[e[0]][0], c[e[1]][0]); ey.push(null, c[e[0]][1], c[e[1]][1]); ez.push(null, c[e[0]][2], c[e[1]][2]); });
    return [
      { type: 'mesh3d', x: [c[0][0],c[1][0],c[2][0],c[3][0], c[4][0],c[5][0],c[6][0],c[7][0]],
          y: [c[0][1],c[1][1],c[2][1],c[3][1], c[4][1],c[5][1],c[6][1],c[7][1]],
          z: [c[0][2],c[1][2],c[2][2],c[3][2], c[4][2],c[5][2],c[6][2],c[7][2]],
          i: meshI, j: meshJ, k: meshK, color: faceColor, flatshading: true,
          showlegend: false, hoverinfo: 'skip' },
      { type: 'scatter3d', mode: 'lines', x: ex, y: ey, z: ez,
          line: {color: edgeColor, width: 3}, showlegend: false, hoverinfo: 'skip' }
    ];
  }

  function removeSelectionBox() {
    if (selectTraces.length > 0) { Plotly.deleteTraces(gd, selectTraces); selectTraces = []; }
  }

  function renderSelectionBox(bounds) {
    if (!bounds) { removeSelectionBox(); return; }
    var newTraces = buildBoxTraces(bounds);
    if (selectTraces.length >= 2) {
      // 更新已有 trace 数据（比删除+重建快得多）
      Plotly.restyle(gd, {
        x: [newTraces[0].x], y: [newTraces[0].y], z: [newTraces[0].z],
        i: [newTraces[0].i], j: [newTraces[0].j], k: [newTraces[0].k]
      }, selectTraces[0]);
      Plotly.restyle(gd, {
        x: [newTraces[1].x], y: [newTraces[1].y], z: [newTraces[1].z]
      }, selectTraces[1]);
    } else {
      // 首次渲染：创建 trace
      removeSelectionBox();
      var base = gd.data.length;
      Plotly.addTraces(gd, newTraces);
      for (var i = 0; i < newTraces.length; i++) selectTraces.push(base + i);
    }
  }

  // ===== 更新显示 =====
  function updateLabels(bounds) {
    // 坐标读数统一保留两位小数（如 3232138.97），不用 SI 缩写
    labelX.textContent = bounds.xMin.toFixed(2) + ' ~ ' + bounds.xMax.toFixed(2) + ' m';
    labelY.textContent = bounds.yMin.toFixed(2) + ' ~ ' + bounds.yMax.toFixed(2) + ' m';
    labelZ.textContent = bounds.zMin.toFixed(2) + ' ~ ' + bounds.zMax.toFixed(2) + ' m';
  }

  // 纯 DOM 更新：拖动过程中每帧执行，不触碰 Plotly（体积计算实测约 0.06ms）
  function updateReadout() {
    var bounds = getBoundsFromSliders();
    currentBounds = bounds;
    updateLabels(bounds);
    var result = computeVolume(bounds);
    var html = '<div class="vol-total">' + formatVolume(result.total) + '</div>';
    html += '<div class="vol-detail">有效网格: ' + result.validCells.toLocaleString() + ' / ' + result.totalCells.toLocaleString()
      + ' (' + (result.totalCells > 0 ? (result.validCells / result.totalCells * 100).toFixed(1) : 0) + '%)'
      + ' | 网格: ' + result.cellArea.toFixed(1) + ' m²</div>';
    if (dg.liths.length > 1) {
      html += '<div class="vol-per-lith">';
      dg.liths.forEach(function(lith) {
        if (activeLiths.indexOf(lith) < 0) return;
        html += lith + ': ' + formatVolume(result.byLith[lith] || 0) + '<br>';
      });
      html += '</div>';
    }
    resultDiv.innerHTML = html;
  }

  // 3D 框体重绘。注意：gl3d 场景没有任何增量更新路径，任何一次 restyle 都会让 plotly
  // 把场景内所有 trace 重新三角化并重传 WebGL，因此这里只在边界真正变化时调用，
  // 且只在拖动结束（change / 指针抬起）后调用，绝不在拖动过程中调用。
  function updateBox(force) {
    if (!active || !currentBounds) return;
    var key = boundsKey(currentBounds);
    if (!force && key === lastBoxKey) return;
    lastBoxKey = key;
    renderSelectionBox(currentBounds);
  }

  function scheduleBoxUpdate() {
    if (_boxTimer !== null) clearTimeout(_boxTimer);
    _boxTimer = setTimeout(function() { _boxTimer = null; updateBox(false); }, BOX_DEBOUNCE_MS);
  }

  // ===== 面板开/关 =====
  function openPanel() {
    active = true;
    panel.classList.add('visible');
    btnActivate.classList.add('active');
    btnActivate.textContent = '📐 关闭估算';
    currentBounds = { xMin: xDataMin, xMax: xDataMax, yMin: yDataMin, yMax: yDataMax, zMin: zDataMin, zMax: zDataMax };
    setSlidersFromBounds(currentBounds);
    resetRotation();
    updateReadout();
    updateBox(true);
  }

  function closePanel() {
    active = false;
    currentBounds = null;
    lastBoxKey = null;
    if (_boxTimer !== null) { clearTimeout(_boxTimer); _boxTimer = null; }
    removeSelectionBox();
    resetRotation();
    panel.classList.remove('visible');
    btnActivate.classList.remove('active');
    btnActivate.textContent = '📐 体积估算';
  }

  btnActivate.addEventListener('click', function() { active ? closePanel() : openPanel(); });
  btnCancel.addEventListener('click', closePanel);
  btnConfirm.addEventListener('click', function() {
    if (!currentBounds) return;
    var result = computeVolume(currentBounds);
    resultDiv.innerHTML = '<div class="vol-total">' + formatVolume(result.total) + '</div><div class="vol-detail">✅ 已确认</div>';
  });

  // ===== 滑块输入（面板打开时始终响应） =====
  // 拖动中：只刷新数值读数（纯 DOM，零 Plotly 调用）；松手：才重绘一次 3D 框体。
  var _sliderRAF = null;
  function onSliderRAF() {
    if (_sliderRAF !== null) return;
    _sliderRAF = requestAnimationFrame(function() { _sliderRAF = null; if (active) updateReadout(); });
  }

  // change 只在指针松开时触发；键盘按住自动重复会连续触发，故再走一层尾随防抖合并。
  function onSliderCommit() {
    if (!active) return;
    updateReadout();
    scheduleBoxUpdate();
  }

  slXMin.addEventListener('input', function() {
    if (parseFloat(this.value) >= parseFloat(slXMax.value)) slXMax.value = Math.min(SLIDER_STEPS, parseFloat(this.value) + 1);
    onSliderRAF();
  });
  slXMin.addEventListener('change', onSliderCommit);
  slXMax.addEventListener('input', function() {
    if (parseFloat(this.value) <= parseFloat(slXMin.value)) slXMin.value = Math.max(0, parseFloat(this.value) - 1);
    onSliderRAF();
  });
  slXMax.addEventListener('change', onSliderCommit);
  slYMin.addEventListener('input', function() {
    if (parseFloat(this.value) >= parseFloat(slYMax.value)) slYMax.value = Math.min(SLIDER_STEPS, parseFloat(this.value) + 1);
    onSliderRAF();
  });
  slYMin.addEventListener('change', onSliderCommit);
  slYMax.addEventListener('input', function() {
    if (parseFloat(this.value) <= parseFloat(slYMin.value)) slYMin.value = Math.max(0, parseFloat(this.value) - 1);
    onSliderRAF();
  });
  slYMax.addEventListener('change', onSliderCommit);
  slZMin.addEventListener('input', function() {
    if (parseFloat(this.value) >= parseFloat(slZMax.value)) slZMax.value = Math.min(SLIDER_STEPS, parseFloat(this.value) + 1);
    onSliderRAF();
  });
  slZMin.addEventListener('change', onSliderCommit);
  slZMax.addEventListener('input', function() {
    if (parseFloat(this.value) <= parseFloat(slZMin.value)) slZMin.value = Math.max(0, parseFloat(this.value) - 1);
    onSliderRAF();
  });
  slZMax.addEventListener('change', onSliderCommit);

  // 旋转角度（绕 X / Y / Z 三个方向，均绕框体中心）
  rotAngle.addEventListener('input', function() {
    rotLabel.textContent = this.value + '°';
    onSliderRAF();
  });
  rotAngle.addEventListener('change', onSliderCommit);
  rotXAngle.addEventListener('input', function() {
    rotXLabel.textContent = this.value + '°';
    onSliderRAF();
  });
  rotXAngle.addEventListener('change', onSliderCommit);
  rotYAngle.addEventListener('input', function() {
    rotYLabel.textContent = this.value + '°';
    onSliderRAF();
  });
  rotYAngle.addEventListener('change', onSliderCommit);

  // 兜底：个别浏览器/触屏场景下 range input 可能不派发 change。指针一抬起就补一次
  // 框体更新；lastBoxKey 会挡掉无变化的情况，因此这是零成本空操作。
  document.addEventListener('pointerup', function() { if (active) scheduleBoxUpdate(); });
  document.addEventListener('mouseup', function() { if (active) scheduleBoxUpdate(); });

  // ===== 面板折叠 =====
  panelToggleBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    panelCollapsed = !panelCollapsed;
    if (panelCollapsed) {
      panelBody.style.display = 'none';
      panelToggleBtn.textContent = '+';
    } else {
      panelBody.style.display = 'block';
      panelToggleBtn.textContent = '−';
    }
  });
  panelHeaderBtn.addEventListener('click', function() {
    panelCollapsed = !panelCollapsed;
    if (panelCollapsed) {
      panelBody.style.display = 'none';
      panelToggleBtn.textContent = '+';
    } else {
      panelBody.style.display = 'block';
      panelToggleBtn.textContent = '−';
    }
  });

  // ===== 初始状态 =====
  initSliders();

  console.log('[体积估算] 已加载，网格: ' + dg.nx + '×' + dg.ny + ', 岩性数: ' + dg.liths.length);

})();
