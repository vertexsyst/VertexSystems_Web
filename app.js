// Function to update dashboard values dynamically
function updateStrategicDashboard() {
    // 1. Simulating data retrieved from active environment scanning
    const activeLaptopsInAD = 65;
    const physicalServerHosts = 6;
    const provisionedVMs = 24;

    // 2. Applying your custom operational definitions
    // Desktop Row
    if (document.getElementById('phys-desktop-box')) document.getElementById('phys-desktop-box').innerText = 5;
    if (document.getElementById('phys-desktop-avail')) document.getElementById('phys-desktop-avail').innerText = 16;
    if (document.getElementById('phys-desktop-repair')) document.getElementById('phys-desktop-repair').innerText = 2;
    if (document.getElementById('phys-desktop-action')) document.getElementById('phys-desktop-action').innerText = 42;
    if (document.getElementById('virt-desktop-vms')) document.getElementById('virt-desktop-vms').innerText = 15;

    // Laptop & Remote Secure Nodes Row
    if (document.getElementById('phys-laptop-box')) document.getElementById('phys-laptop-box').innerText = 8;
    if (document.getElementById('phys-laptop-avail')) document.getElementById('phys-laptop-avail').innerText = 24;
    if (document.getElementById('phys-laptop-repair')) document.getElementById('phys-laptop-repair').innerText = 4;
    if (document.getElementById('phys-laptop-action')) document.getElementById('phys-laptop-action').innerText = activeLaptopsInAD;
    if (document.getElementById('virt-laptop-vms')) document.getElementById('virt-laptop-vms').innerText = 72; // Populates Remote Secure Nodes!

    // Switch Row
    if (document.getElementById('phys-switch-box')) document.getElementById('phys-switch-box').innerText = 1;
    if (document.getElementById('phys-switch-avail')) document.getElementById('phys-switch-avail').innerText = 2;
    if (document.getElementById('phys-switch-repair')) document.getElementById('phys-switch-repair').innerText = 0;
    if (document.getElementById('phys-switch-action')) document.getElementById('phys-switch-action').innerText = 8;
    if (document.getElementById('virt-switch-vms')) document.getElementById('virt-switch-vms').innerText = 12;

    // Server Row
    if (document.getElementById('phys-server-box')) document.getElementById('phys-server-box').innerText = 2;
    if (document.getElementById('phys-server-avail')) document.getElementById('phys-server-avail').innerText = 4;
    if (document.getElementById('phys-server-repair')) document.getElementById('phys-server-repair').innerText = 1;
    if (document.getElementById('phys-server-action')) document.getElementById('phys-server-action').innerText = physicalServerHosts;
    if (document.getElementById('virt-server-vms')) document.getElementById('virt-server-vms').innerText = provisionedVMs;

    // 3. Calculating Top Level Macro Metrics via formulas
    const healthIndex = 99.4;
    const blockedThreats = 1420;
    const liabilitySaved = blockedThreats * 30;

    if (document.getElementById('health-index')) document.getElementById('health-index').innerText = healthIndex + "%";
    if (document.getElementById('threat-tracker')) document.getElementById('threat-tracker').innerText = blockedThreats.toLocaleString();
    if (document.getElementById('financial-value')) document.getElementById('financial-value').innerText = "$" + liabilitySaved.toLocaleString();
}

// Execute the function
updateStrategicDashboard();