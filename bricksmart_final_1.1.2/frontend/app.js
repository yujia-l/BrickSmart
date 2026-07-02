const API = window.location.origin;

async function loadInventory() {
  const response = await fetch(`${API}/api/inventory/default`);
  const payload = await response.json();
  document.querySelector("#inventory").innerHTML = Object.entries(payload.blocks).map(([name, count]) => `
    <article class="inventory-card">
      <small>${name}</small><strong>${count}</strong><span>available</span>
    </article>`).join("");
  return payload;
}

async function uploadModel() {
  const status = document.querySelector("#upload-status");
  const modelId = document.querySelector("#model-id").value.trim();
  const file = document.querySelector("#model-file").files[0];
  if (!modelId || !file) throw new Error("Choose an OBJ file and enter a model ID");
  status.textContent = "Uploading…";
  const body = new FormData();
  body.append("model_id", modelId);
  body.append("file", file);
  const response = await fetch(`${API}/api/models/upload`, { method: "POST", body });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Upload failed");
  document.querySelector("#model-uri").value = result.canonical_uri;
  status.textContent = `${result.canonical_uri} · ${result.sha256.slice(0, 12)}…`;
}


async function uploadContract() {
  const status = document.querySelector("#contract-status");
  const contractId = document.querySelector("#contract-id").value.trim();
  const contextFile = document.querySelector("#contract-file").files[0];
  const confirmations = document.querySelector("#confirmation-file").files[0];
  if (!contractId || !contextFile) throw new Error("Choose a task-context JSON and enter a contract ID");
  status.textContent = "Registering…";
  const body = new FormData();
  body.append("contract_id", contractId);
  body.append("task_context", contextFile);
  if (confirmations) body.append("confirmations", confirmations);
  const response = await fetch(`${API}/api/contracts/upload`, { method: "POST", body });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Contract registration failed");
  document.querySelector("#task-context").value = result.canonical_uri;
  status.textContent = `${result.canonical_uri} · ${result.context_sha256.slice(0, 12)}…`;
}

async function runModelBuild() {
  const status = document.querySelector("#model-status");
  status.textContent = "Running…";
  const taskContext = document.querySelector("#task-context").value.trim();
  const inventoryPath = document.querySelector("#inventory-path").value.trim();
  const modelUri = document.querySelector("#model-uri").value.trim();
  const response = await fetch(`${API}/api/model/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contract_uri: taskContext,
      model_uri: modelUri || null,
      inventory_path: inventoryPath || null,
      clean_output: true,
      allow_incomplete: false
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Model build failed");
  status.textContent = result.final_status;
  const contract = result.model_contract || {};
  document.querySelector("#model-metrics").innerHTML = [
    ["Model ID", contract.model_id || "—"],
    ["Model source", contract.source_model_uri || "—"],
    ["Final blocks", result.final_block_count],
    ["Structural modules", result.structural_segment_count],
    ["Direct joins", result.direct_structural_join_count],
    ["Symmetry", result.combined_symmetry_complete ? "PASS" : "Not required / fail"],
    ["Inventory", result.inventory_valid ? "PASS" : "FAIL"],
    ["True build steps", result.true_build_step_count]
  ].map(([label, value]) => `<article class="metric"><small>${label}</small><strong>${value}</strong></article>`).join("");
  document.querySelector("#model-output").textContent = `Artifacts: ${result.artifacts_dir}`;
  document.querySelector("#model-run").textContent = `Run: ${result.run_id} · ${result.run_dir}`;
}

async function runCandidatePlan() {
  const inventory = await loadInventory();
  const problemResponse = await fetch(`${API}/api/problem/sample`);
  const problem = await problemResponse.json();
  const response = await fetch(`${API}/api/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      inventory_mode: inventory.inventory_mode,
      inventory_id: inventory.inventory_id,
      quantities: inventory.blocks,
      scarcity_weight: problem.scarcity_weight,
      fail_on_required_group: problem.fail_on_required_group,
      groups: problem.groups
    })
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Planning failed");
  document.querySelector("#candidate-status").textContent = result.status;
  document.querySelector("#decisions").innerHTML = result.decisions.map(decision => `
    <tr><td>${decision.group_id}</td><td>${decision.selected_candidate_id ?? "—"}</td><td>${decision.status}</td><td><code>${JSON.stringify(decision.requirements)}</code></td></tr>`).join("");
}

document.querySelector("#upload-model").addEventListener("click", () => uploadModel().catch(error => {
  document.querySelector("#upload-status").textContent = error.message;
}));
document.querySelector("#upload-contract").addEventListener("click", () => uploadContract().catch(error => {
  document.querySelector("#contract-status").textContent = error.message;
}));
document.querySelector("#run-model").addEventListener("click", () => runModelBuild().catch(error => {
  document.querySelector("#model-status").textContent = error.message;
}));
document.querySelector("#run-candidates").addEventListener("click", () => runCandidatePlan().catch(error => {
  document.querySelector("#candidate-status").textContent = error.message;
}));

loadInventory().catch(() => {
  document.querySelector("#model-status").textContent = "Start the API to use this page.";
});
