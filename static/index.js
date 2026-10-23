document.addEventListener('DOMContentLoaded', () => {
    const joystick = document.getElementsByClassName('joystick')[0];
    const stick = document.getElementsByClassName('stick')[0];
    const status = document.getElementsByClassName('status')[0];
    const statusText = document.getElementsByClassName('status-text')[0];
    const rx = document.getElementsByClassName('rx')[0];
    const ry = document.getElementsByClassName('ry')[0];

    const radius = 75;          // how far the stick can travel from center (px)
    const SEND_INTERVAL = 50;   // ms -> 20 commands/sec, also acts as a heartbeat

    let dragging = false;
    let pointerId = null;
    let animationFrameId = null;
    let cmd = { x: 0, y: 0 };   // normalized -1..1, y positive = forward

    // ---------------------------------------------------------------------
    // WebSocket
    // When the page is served by the Pico, location.host is the Pico's IP.
    // If you open index.html from your computer instead, add ?host=<pico ip>
    // to the URL (defaults to 192.168.4.1, the Pico's access point address).
    // ---------------------------------------------------------------------
    const params = new URLSearchParams(location.search);
    const host = params.get('host') || location.host || '192.168.4.1';
    let socket = null;
    let retryDelay = 500;

    const setStatus = (cls, text) => {
        status.classList.remove('connected', 'disconnected');
        if (cls) status.classList.add(cls);
        statusText.textContent = text;
    };

    const connect = () => {
        setStatus(null, `Connecting to ${host}...`);
        socket = new WebSocket(`ws://${host}/direction`);
        socket.addEventListener('open', () => {
            retryDelay = 500;
            setStatus('connected', `Connected to ${host}`);
        });
        socket.addEventListener('close', () => {
            setStatus('disconnected', 'Disconnected, retrying...');
            setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 5000);
        });
        socket.addEventListener('error', () => socket.close());
    };

    const send = () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(cmd));
        }
    };

    // Send on a fixed clock, even when the stick isn't moving. The Pico stops
    // the motors if it doesn't hear from us for 500 ms, so this keeps it alive.
    setInterval(send, SEND_INTERVAL);

    // ---------------------------------------------------------------------
    // Joystick
    // ---------------------------------------------------------------------
    const moveStick = (x, y) => {
        stick.style.transform = `translate(${x}px, ${y}px)`;
        cmd = { x: +(x / radius).toFixed(3), y: +(-y / radius).toFixed(3) };
        rx.textContent = cmd.x.toFixed(2);
        ry.textContent = cmd.y.toFixed(2);
    };

    const resetStickPosition = () => {
        moveStick(0, 0);
        send();  // stop immediately instead of waiting for the next tick
    };

    const handleMovement = (clientX, clientY) => {
        const rect = joystick.getBoundingClientRect();
        let x = clientX - (rect.left + rect.width / 2);   // offset from center
        let y = clientY - (rect.top + rect.height / 2);

        // Keep the stick inside the circle (scale back along the same angle)
        const current_radius = Math.sqrt(x * x + y * y);
        if (current_radius > radius) {
            x *= radius / current_radius;
            y *= radius / current_radius;
        }

        if (!animationFrameId) {
            animationFrameId = requestAnimationFrame(() => {
                if (dragging) moveStick(x, y);
                animationFrameId = null;
            });
        }
    };

    // Pointer events cover mouse, touch and pen with one set of handlers.
    joystick.addEventListener('pointerdown', (e) => {
        if (dragging) return;              // ignore a second finger
        dragging = true;
        pointerId = e.pointerId;
        joystick.setPointerCapture(pointerId);  // keep getting moves outside the circle
        joystick.classList.add('active');
        handleMovement(e.clientX, e.clientY);
    });

    joystick.addEventListener('pointermove', (e) => {
        if (dragging && e.pointerId === pointerId) handleMovement(e.clientX, e.clientY);
    });

    const release = (e) => {
        if (!dragging || e.pointerId !== pointerId) return;
        dragging = false;
        pointerId = null;
        joystick.classList.remove('active');
        resetStickPosition();
    };
    joystick.addEventListener('pointerup', release);
    joystick.addEventListener('pointercancel', release);
    joystick.addEventListener('lostpointercapture', release);

    // If the tab is hidden (phone locked, app switched), stop the robot.
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            dragging = false;
            joystick.classList.remove('active');
            resetStickPosition();
        }
    });

    connect();
});
