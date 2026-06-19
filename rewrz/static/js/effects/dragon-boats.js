/**
 * 龙舟横渡特效
 * 适合端午节场景
 */

class DragonBoatsEffect {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.boats = [];
        this.animationId = null;
    }

    init() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'dragon-boats-canvas';
        this.canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9997;';
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.ctx = this.canvas.getContext('2d');
        document.body.appendChild(this.canvas);
        this.boats = [
            { x: -160, y: this.canvas.height * 0.72, speed: 1.4, scale: 1 },
            { x: this.canvas.width + 160, y: this.canvas.height * 0.56, speed: -1.1, scale: 0.82 },
        ];
        this.animate();
    }

    drawBoat(boat) {
        this.ctx.save();
        this.ctx.translate(boat.x, boat.y);
        this.ctx.scale(boat.scale * (boat.speed > 0 ? 1 : -1), boat.scale);
        this.ctx.fillStyle = '#8b1e3f';
        this.ctx.beginPath();
        this.ctx.moveTo(-80, 0);
        this.ctx.quadraticCurveTo(-10, -24, 72, 0);
        this.ctx.quadraticCurveTo(-8, 22, -80, 0);
        this.ctx.fill();
        this.ctx.fillStyle = '#f0c94d';
        this.ctx.beginPath();
        this.ctx.arc(-72, -8, 10, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.fillRect(-12, -26, 3, 22);
        this.ctx.fillRect(12, -24, 3, 20);
        this.ctx.restore();
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.boats.forEach((boat) => {
            boat.x += boat.speed;
            if (boat.speed > 0 && boat.x > this.canvas.width + 200) boat.x = -200;
            if (boat.speed < 0 && boat.x < -200) boat.x = this.canvas.width + 200;
            this.drawBoat(boat);
        });
        this.animationId = requestAnimationFrame(() => this.animate());
    }

    stop() {
        if (this.animationId) cancelAnimationFrame(this.animationId);
        if (this.canvas) document.body.removeChild(this.canvas);
        this.canvas = null;
        this.boats = [];
        this.animationId = null;
    }
}

window.DragonBoatsEffect = DragonBoatsEffect;
