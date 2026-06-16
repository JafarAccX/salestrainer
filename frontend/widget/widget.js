/* widget.js */
const widgetHtml = `
<div class="lk-widget-container" id="lk-widget">
  <div class="lk-widget-header">
    <span>Sales Trainer</span>
    <button onclick="toggleWidget()">X</button>
  </div>
  <div class="lk-widget-body">
    <div class="visualizer" id="visualizer">
      <div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div>
    </div>
    <button id="widgetStartBtn" onclick="startWidgetSession()">Start Call</button>
    <iframe id="lk-iframe" style="display:none; width:100%; height:300px; border:none;"></iframe>
  </div>
</div>
<button id="widgetToggleBtn" style="position:fixed; bottom:20px; right:20px;" onclick="toggleWidget()">Chat</button>
`;

document.body.insertAdjacentHTML('beforeend', widgetHtml);

function toggleWidget() {
  const w = document.getElementById('lk-widget');
  w.style.display = w.style.display === 'none' ? 'block' : 'none';
}

async function startWidgetSession() {
  const moduleId = document.getElementById('moduleSelect').value || null;
  const data = await request('/api/mock-call/start', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sales_rep_id: 'widget-rep', module_id: moduleId }),
  });

  if (data.connection_link) {
    const iframe = document.getElementById('lk-iframe');
    iframe.src = data.connection_link;
    iframe.style.display = 'block';
    document.getElementById('widgetStartBtn').style.display = 'none';
    
    // Simulate visualizer
    document.querySelectorAll('.bar').forEach(b => b.classList.add('active'));
  }
}
