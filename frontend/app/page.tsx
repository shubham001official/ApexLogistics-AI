"use client";
import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Master Coordinate Dictionary - Pan-India V3
const NODE_COORDS: Record<string, [number, number]> = {
  "JNPT": [72.9490, 18.9490],
  "MUNDRA": [69.7110, 22.7440],
  "KOLKATA": [88.3639, 22.5726],
  "CHAKAN": [73.8625, 18.7623],
  "BHIWANDI": [73.0600, 19.3000],
  "SRIPERUMBUDUR": [79.9460, 12.9670],
  "DELHI": [77.1025, 28.7041],
  "BANGALORE": [77.5946, 12.9716],
  "HYDERABAD": [78.4867, 17.3850],
  "SUP_": [73.8100, 18.7800], // Generic local supplier fallback
};

const API_BASE = "http://127.0.0.1:8000/api/v1";

const getCoord = (identifier: string): [number, number] => {
  for (const [key, val] of Object.entries(NODE_COORDS)) {
    if (identifier.includes(key)) return val;
  }
  return NODE_COORDS["JNPT"]; // Safe fallback
};

export default function Dashboard() {
  const mapContainer = useRef(null);
  const map = useRef<maplibregl.Map | null>(null);

  // Application State
  const [shipments, setShipments] = useState<any[]>([]);
  const [selectedShipment, setSelectedShipment] = useState<any | null>(null);
  const [telemetry, setTelemetry] = useState<any | null>(null);
  const [riskData, setRiskData] = useState<any | null>(null);
  const [isChaosActive, setIsChaosActive] = useState(false);

  // CRUD Modal State
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newRouteInput, setNewRouteInput] = useState("JNPT_TO_BANGALORE");

  // AI Workflow State
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [agentResult, setAgentResult] = useState<any>(null);
  const [isCommitRunning, setIsCommitRunning] = useState(false);
  const [commitSuccess, setCommitSuccess] = useState(false);

  // 1. Initialize Map
  useEffect(() => {
    if (map.current) return;
    map.current = new maplibregl.Map({
      container: mapContainer.current!,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: [78.9629, 20.5937], // Centered on India
      zoom: 4.5
    });

    map.current.on('load', () => {
      Object.entries(NODE_COORDS).forEach(([key, coords]) => {
        if (key.includes("SUP_")) return;
        new maplibregl.Marker({ color: "#1e293b" })
          .setLngLat(coords)
          .setPopup(new maplibregl.Popup({ offset: 25 }).setText(key.replace(/_/g, " ")))
          .addTo(map.current!);
      });
      fetchShipments();
    });
  }, []);

  // 2. Fetch Active Shipments
  const fetchShipments = async () => {
    try {
      const res = await fetch(`${API_BASE}/shipments`);
      const data = await res.json();
      setShipments(data.shipments || []);
      if (data.shipments?.length > 0 && !selectedShipment) {
        handleSelectShipment(data.shipments[0]);
      }
    } catch (err) {
      console.error("Fetch shipments error", err);
    }
  };

  // 3. Handle Shipment Selection
  const handleSelectShipment = async (shipment: any) => {
    setSelectedShipment(shipment);
    setAgentResult(null);
    setCommitSuccess(false);
    drawRoute(shipment.route, shipment.status);
    fetchTelemetryAndRisk(shipment.route);
  };

  const drawRoute = async (routeStr: string, status: string) => {
    if (!map.current) return;
    const parts = routeStr.split("_TO_");
    const source = getCoord(parts[0] || "");
    const dest = getCoord(parts[1] || "");

    try {
      const osrmUrl = `http://router.project-osrm.org/route/v1/driving/${source[0]},${source[1]};${dest[0]},${dest[1]}?overview=full&geometries=geojson`;
      const res = await fetch(osrmUrl);
      const data = await res.json();
      const routeGeoJSON = data.routes[0].geometry;

      if (map.current.getSource('active-route')) {
        (map.current.getSource('active-route') as maplibregl.GeoJSONSource).setData(routeGeoJSON);
      } else {
        map.current.addSource('active-route', { type: 'geojson', data: routeGeoJSON });
        map.current.addLayer({
          'id': 'active-route-line',
          'type': 'line',
          'source': 'active-route',
          'layout': { 'line-join': 'round', 'line-cap': 'round' },
          'paint': { 'line-color': '#2563eb', 'line-width': 5 }
        });
      }

      const routeColor = status === 'REROUTED' ? '#10b981' : status === 'DELAYED' ? '#f59e0b' : '#2563eb';
      map.current.setPaintProperty('active-route-line', 'line-color', routeColor);
      map.current.fitBounds([source, dest], { padding: 150 });
    } catch (err) {
      console.error("OSRM Error:", err);
    }
  };

  const fetchTelemetryAndRisk = async (routeId: string) => {
    try {
      const telRes = await fetch(`${API_BASE}/telemetry/live/${routeId}`);
      if (!telRes.ok) return;
      const telData = await telRes.json();
      setTelemetry(telData);
      setIsChaosActive(telData?.toll_queue_m > 1000);

      const riskRes = await fetch(`${API_BASE}/predict-risk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(telData)
      });
      if (!riskRes.ok) return;
      const riskResult = await riskRes.json();
      setRiskData(riskResult);

      if (riskResult?.alert_triggered && map.current) {
        map.current.setPaintProperty('active-route-line', 'line-color', '#ef4444');
      }
    } catch (err) {
      console.error("Telemetry/Risk Error", err);
    }
  };

  // 4. Advanced CRUD Operations
  const handleCreateShipment = async () => {
    try {
      await fetch(`${API_BASE}/shipments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ po_id: "DEMO_PO", current_route: newRouteInput })
      });
      setIsCreateModalOpen(false);
      fetchShipments();
    } catch (err) { console.error(err); }
  };

  const handleDeleteShipment = async (id: string) => {
    try {
      // Optimistic update
      setShipments(prev => prev.filter(s => s.id !== id));
      setSelectedShipment(null);
      if (map.current?.getSource('active-route')) {
        (map.current.getSource('active-route') as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: [] });
      }
      await fetch(`${API_BASE}/shipments/${id}`, { method: 'DELETE' });
    } catch (err) { console.error(err); }
  };

  const handleUpdateStatus = async (id: string, newStatus: string) => {
    try {
      // Optimistic Update
      setShipments(prev => prev.map(s => s.id === id ? { ...s, status: newStatus } : s));
      if (selectedShipment?.id === id) {
        setSelectedShipment({ ...selectedShipment, status: newStatus });
      }
      await fetch(`${API_BASE}/shipments/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
    } catch (err) { console.error(err); }
  };

  // 5. Chaos & Agent Flows
  const toggleChaos = async () => {
    if (!selectedShipment) return;
    const endpoint = isChaosActive ? "clear-obstacle" : "trigger-obstacle";
    try {
      await fetch(`${API_BASE}/demo/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ route_id: selectedShipment.route })
      });
      fetchTelemetryAndRisk(selectedShipment.route);
    } catch (err) { console.error(err); }
  };

  const handleTriggerAI = async () => {
    setIsAgentRunning(true);
    try {
      const response = await fetch(`${API_BASE}/reroute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          impacted_route: selectedShipment.route,
          destination_hub: selectedShipment.route.split("_TO_")[1] || "CHAKAN_AUTO_CLUSTER",
          original_cost: selectedShipment.value
        })
      });
      const data = await response.json();
      setAgentResult(data);
    } catch (error) { console.error(error); }
    finally { setIsAgentRunning(false); }
  };

  const handleCommit = async () => {
    setIsCommitRunning(true);
    try {
      await fetch(`${API_BASE}/reroute/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shipment_id: selectedShipment.id,
          new_supplier_id: agentResult.proposed_reroute.selected_supplier_id,
          new_cost: agentResult.proposed_reroute.estimated_cost_inr,
          impacted_route: selectedShipment.route
        })
      });
      setCommitSuccess(true);
      fetchShipments(); // Hard sync after graph mutation
    } catch (err) { console.error(err); }
    finally { setIsCommitRunning(false); }
  };

  // Status Badge Helper
  const getStatusStyle = (status: string) => {
    switch (status) {
      case 'REROUTED': return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'DELAYED': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'CUSTOMS_HOLD': return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'DELIVERED': return 'bg-slate-200 text-slate-800 border-slate-300';
      default: return 'bg-blue-50 text-blue-800 border-blue-200';
    }
  };

  return (
    <div className="relative w-full h-screen font-sans bg-slate-50 flex overflow-hidden">

      {/* Left Sidebar: Advanced CRUD */}
      <div className="w-80 bg-white border-r border-slate-200 flex flex-col z-10 shadow-[4px_0_24px_rgba(0,0,0,0.05)]">
        <div className="p-5 bg-slate-900 text-white">
          <h1 className="text-xl font-bold tracking-tight">ResiliNet-IN</h1>
          <p className="text-xs text-slate-400 mt-1">Enterprise Command Center</p>
        </div>

        <div className="p-4 border-b border-slate-100 bg-slate-50/50">
          <button
            onClick={() => setIsCreateModalOpen(!isCreateModalOpen)}
            className="w-full bg-slate-900 hover:bg-slate-800 text-white text-sm font-bold py-2.5 rounded shadow-sm transition-all"
          >
            + Dispatch New Shipment
          </button>

          {isCreateModalOpen && (
            <div className="mt-3 p-4 bg-white border border-slate-200 rounded-lg shadow-lg animate-in slide-in-from-top-2">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-2">Select National Corridor</label>
              <select
                value={newRouteInput}
                onChange={e => setNewRouteInput(e.target.value)}
                className="w-full border border-slate-200 p-2 text-sm mb-3 rounded focus:outline-none focus:border-blue-500 bg-slate-50"
              >
                <option value="JNPT_TO_BANGALORE">JNPT ➔ Bangalore</option>
                <option value="MUNDRA_TO_DELHI">Mundra ➔ Delhi NCR</option>
                <option value="KOLKATA_TO_HYDERABAD">Kolkata ➔ Hyderabad</option>
                <option value="DELHI_TO_CHAKAN">Delhi NCR ➔ Chakan</option>
                <option value="BANGALORE_TO_SRIPERUMBUDUR">Bangalore ➔ Sriperumbudur</option>
              </select>
              <button
                onClick={handleCreateShipment}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs py-2 rounded font-bold transition-all"
              >
                Generate PO & Dispatch
              </button>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/30">
          <h2 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">Active Network</h2>
          {shipments.map(s => (
            <div
              key={s.id}
              onClick={() => handleSelectShipment(s)}
              className={`p-3.5 rounded-lg border cursor-pointer transition-all ${selectedShipment?.id === s.id ? 'bg-white border-blue-500 shadow-md ring-1 ring-blue-500/20' : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-sm'}`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-slate-800 text-sm">{s.id.replace("SHP_", "")}</span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${getStatusStyle(s.status)}`}>
                  {s.status.replace("_", " ")}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium mb-1 flex justify-between">
                <span>Freight Value:</span>
                <span className="text-slate-700 font-bold">₹{s.value?.toLocaleString()}</span>
              </p>
              <p className="text-[11px] text-slate-400 font-mono truncate bg-slate-50 p-1 rounded mt-2">{s.route}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Center Map */}
      <div className="flex-1 relative bg-slate-100">
        <div ref={mapContainer} className="absolute inset-0 z-0" style={{ width: '100%', height: '100%' }} />
      </div>

      {/* Right Sidebar: Command Center & AI Matrix */}
      {selectedShipment && telemetry && riskData && (
        <div className="absolute top-6 right-6 w-[420px] bg-white shadow-2xl rounded-xl border border-slate-200 z-20 flex flex-col max-h-[90vh] overflow-hidden">

          {/* Telemetry Header */}
          <div className={`${riskData?.alert_triggered ? 'bg-red-50 border-red-100' : 'bg-slate-900 border-slate-800'} border-b p-5 transition-colors`}>
            <div className="flex justify-between items-center mb-2">
              <h3 className={`font-bold ${riskData?.alert_triggered ? 'text-red-700' : 'text-white'}`}>Live Telemetry & Risk Engine</h3>
              <span className={`px-2.5 py-1 rounded text-xs font-bold ${riskData?.alert_triggered ? 'bg-red-600 text-white animate-pulse shadow-[0_0_10px_rgba(220,38,38,0.5)]' : 'bg-slate-800 text-emerald-400 border border-slate-700'}`}>
                Risk Score: {riskData?.risk_score?.toFixed(2) ?? '0.00'}
              </span>
            </div>
            <p className={`text-xs font-mono break-all ${riskData?.alert_triggered ? 'text-red-600/80' : 'text-slate-400'}`}>{selectedShipment.route}</p>
          </div>

          <div className="p-5 space-y-5 overflow-y-auto">

            {/* Granular Status Control */}
            <div className="flex gap-2">
              <select
                value={selectedShipment.status}
                onChange={(e) => handleUpdateStatus(selectedShipment.id, e.target.value)}
                className="flex-1 bg-slate-50 border border-slate-200 text-slate-700 text-xs font-bold py-1.5 px-2 rounded focus:outline-none"
              >
                <option value="IN_TRANSIT">In Transit</option>
                <option value="DELAYED">Delayed</option>
                <option value="CUSTOMS_HOLD">Customs Hold</option>
                <option value="DELIVERED">Delivered</option>
              </select>
              <button
                onClick={() => handleDeleteShipment(selectedShipment.id)}
                className="bg-white hover:bg-red-50 text-red-600 text-xs font-bold py-1.5 px-3 border border-red-200 rounded transition-colors"
              >
                Drop
              </button>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                <p className="text-[10px] uppercase text-slate-400 font-bold mb-1">Precipitation</p>
                <p className="font-mono text-slate-800 text-lg">{telemetry?.rainfall_mm ?? 0} <span className="text-xs text-slate-500">mm</span></p>
              </div>
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                <p className="text-[10px] uppercase text-slate-400 font-bold mb-1">Wind Speed</p>
                <p className="font-mono text-slate-800 text-lg">{telemetry?.wind_speed_kmh ?? 0} <span className="text-xs text-slate-500">km/h</span></p>
              </div>
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 col-span-2 flex justify-between items-end">
                <div>
                  <p className="text-[10px] uppercase text-slate-400 font-bold mb-1">Highway / Toll Queue</p>
                  <p className="font-mono text-slate-800 text-lg">{telemetry?.toll_queue_m ?? 0} <span className="text-xs text-slate-500">meters</span></p>
                </div>
                <div className="pb-1">
                  {telemetry?.toll_queue_m > 1000 && <span className="text-[10px] font-bold text-red-500 uppercase px-2 py-0.5 bg-red-100 rounded">Severe Traffic</span>}
                </div>
              </div>
            </div>

            {/* The Chaos Button */}
            <div className="pt-2">
              <button
                onClick={toggleChaos}
                className={`w-full py-3 px-4 rounded-lg text-sm font-bold shadow-sm transition-all ${isChaosActive ? 'bg-slate-800 text-white hover:bg-slate-700' : 'bg-orange-50 text-orange-700 border border-orange-300 hover:bg-orange-100'}`}
              >
                {isChaosActive ? "Clear Obstacle (Restore Network)" : "⚡ Simulate Severe Roadblock"}
              </button>
            </div>

            {/* AI Strategy Matrix */}
            {riskData?.alert_triggered && selectedShipment.status !== 'REROUTED' && !commitSuccess && (
              <div className="pt-5 border-t border-slate-100 animate-in fade-in">
                {!agentResult && !isAgentRunning && (
                  <div className="bg-red-50 rounded-lg p-4 border border-red-100">
                    <p className="text-xs text-red-700 mb-3 font-semibold leading-relaxed">System has flagged a high probability of SLA breach. ERP manual rerouting bypassed.</p>
                    <button
                      onClick={handleTriggerAI}
                      className="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-2.5 rounded shadow-sm transition-colors text-sm"
                    >
                      Engage LangGraph Orchestrator
                    </button>
                  </div>
                )}

                {isAgentRunning && (
                  <div className="flex flex-col items-center justify-center py-6 bg-slate-50 rounded-lg border border-slate-100">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-slate-900 mb-3"></div>
                    <p className="text-xs font-bold text-slate-500 uppercase tracking-widest animate-pulse">Querying Knowledge Graph...</p>
                  </div>
                )}

                {agentResult && !isCommitRunning && (
                  <div className="bg-white border border-emerald-200 shadow-[0_4px_20px_rgba(16,185,129,0.1)] rounded-lg overflow-hidden">
                    <div className="bg-emerald-50 px-4 py-3 border-b border-emerald-100">
                      <h4 className="font-bold text-emerald-900 text-sm flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                        AI Recommended Strategy
                      </h4>
                    </div>

                    <div className="p-4">
                      <p className="text-xs text-slate-500 mb-1">Target Backup Supplier</p>
                      <p className="text-sm font-bold text-slate-900 mb-4">{agentResult?.proposed_reroute?.selected_supplier_id}</p>

                      {/* Cost Comparison Matrix */}
                      <div className="grid grid-cols-2 gap-3 mb-4">
                        <div className="bg-slate-50 p-2.5 rounded border border-slate-100">
                          <p className="text-[10px] uppercase text-slate-400 font-bold mb-1">Original Liability</p>
                          <p className="font-mono text-slate-500 line-through text-sm">₹{selectedShipment.value?.toLocaleString()}</p>
                        </div>
                        <div className="bg-emerald-50 p-2.5 rounded border border-emerald-200">
                          <p className="text-[10px] uppercase text-emerald-600 font-bold mb-1">New Est. Freight</p>
                          <p className="font-mono text-emerald-700 font-bold text-sm">₹{agentResult?.proposed_reroute?.estimated_cost_inr?.toLocaleString()}</p>
                        </div>
                      </div>

                      <div className="bg-slate-50 rounded p-3 mb-4 border-l-2 border-emerald-400">
                        <p className="text-[11px] text-slate-600 italic leading-relaxed">
                          "{agentResult?.proposed_reroute?.justification}"
                        </p>
                      </div>

                      <button
                        onClick={handleCommit}
                        className="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-lg shadow-md transition-all text-sm"
                      >
                        Approve & Mutate Graph State
                      </button>
                    </div>
                  </div>
                )}

                {isCommitRunning && (
                  <div className="flex flex-col items-center justify-center py-6 bg-slate-50 rounded-lg border border-slate-100">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-emerald-500 mb-3"></div>
                    <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest animate-pulse">Writing to Neo4j...</p>
                  </div>
                )}
              </div>
            )}

            {/* Success State */}
            {(commitSuccess || selectedShipment.status === 'REROUTED') && (
              <div className="pt-6 pb-2 text-center animate-in zoom-in-95">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-100 mb-3 border border-emerald-200 shadow-sm text-emerald-600 text-2xl font-bold">
                  ✓
                </div>
                <h4 className="text-emerald-800 font-bold text-lg">Graph Mutated</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-[250px] mx-auto">The AI's strategy has been successfully committed to the Neo4j database.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}