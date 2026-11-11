// Mobile Navigation
const hamburger = document.querySelector(".hamburger");
const navMenu = document.querySelector(".nav-menu");

hamburger.addEventListener("click", () => {
  hamburger.classList.toggle("active");
  navMenu.classList.toggle("active");
});

// Close mobile menu when clicking on a link
document.querySelectorAll(".nav-menu a").forEach((n) =>
  n.addEventListener("click", () => {
    hamburger.classList.remove("active");
    navMenu.classList.remove("active");
  })
);

// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", function (e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute("href"));
    if (target) {
      target.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  });
});

// Interactive Console System
class ConsoleAssistant {
  constructor() {
    this.consoleBody = document.getElementById("console-body");
    this.consoleInput = document.getElementById("console-input");
    this.initializeConsole();
    this.setupEventListeners();
  }

  initializeConsole() {
    this.responses = {
      // Comandos de ajuda
      help: [
        "Comandos disponíveis:",
        "• sobre - Informações sobre mim",
        "• skills - Minhas habilidades técnicas",
        "• experiencia - Minha experiência profissional",
        "• projetos - Projetos que desenvolvi",
        "• contato - Como entrar em contato",
        "• lua - Sobre minha experiência com Lua",
        "• devops - Sobre DevOps e infraestrutura",
        "• frontend - Tecnologias frontend",
        "• backend - Tecnologias backend",
        "• clear - Limpar terminal",
      ],

      // Informações pessoais
      sobre: [
        "Sou um desenvolvedor Full Stack apaixonado por tecnologia.",
        "Trabalho com desenvolvimento web há mais de 5 anos.",
        "Especialista em Lua (senior), DevOps e infraestrutura.",
        "Gosto de criar soluções completas, do frontend ao deploy.",
      ],

      "quem é você": [
        "Eu sou o Ruts, um desenvolvedor Full Stack.",
        "Trabalho com tecnologias web modernas e infraestrutura.",
        "Minha especialidade é Lua, mas domino diversas tecnologias.",
      ],

      // Skills técnicas
      skills: [
        "Frontend: HTML5, CSS3, JavaScript, jQuery, React",
        "Backend: Lua (Senior), Node.js, Python, PHP",
        "DevOps: Docker, Kubernetes, CI/CD, AWS",
        "Infraestrutura: Redes, Virtualização, Monitoramento",
      ],

      lua: [
        "Sou desenvolvedor senior em Lua há mais de 3 anos.",
        "Uso Lua para automação, scripting e desenvolvimento de APIs.",
        "Experiência com OpenResty, NGINX + Lua e sistemas embarcados.",
        "É uma linguagem incrível para performance e simplicidade!",
      ],

      devops: [
        "Experiência com containerização usando Docker e Kubernetes.",
        "Implemento pipelines CI/CD com Jenkins e GitHub Actions.",
        "Trabalho com AWS, provisionamento com Terraform.",
        "Monitoramento com Prometheus, Grafana e ELK Stack.",
      ],

      frontend: [
        "HTML5 semântico e acessível",
        "CSS3 moderno com Flexbox e Grid",
        "JavaScript ES6+ e frameworks como React",
        "Experiência com jQuery para projetos legados",
        "Responsive design e mobile-first approach",
      ],

      backend: [
        "Lua (Senior) - Minha especialidade principal",
        "Node.js para APIs REST e aplicações real-time",
        "Python para automação e data processing",
        "PHP para sistemas web tradicionais",
        "Databases: MySQL, PostgreSQL, MongoDB, Redis",
      ],

      // Experiência
      experiencia: [
        "5+ anos como desenvolvedor Full Stack",
        "Projetos em e-commerce, sistemas corporativos",
        "Automação de infraestrutura e DevOps",
        "Consultoria em arquitetura de sistemas",
      ],

      projetos: [
        "Sistema de E-commerce completo com React e Node.js",
        "Infraestrutura Cloud automatizada com Terraform",
        "Dashboard de monitoramento em tempo real",
        "APIs de alta performance em Lua",
        "Sistemas de automação DevOps",
      ],

      // Contato
      contato: [
        "Email: ruts@dev.com",
        "LinkedIn: linkedin.com/in/ruts",
        "GitHub: github.com/ruts",
        "Localização: Brasil",
      ],

      // Comandos especiais
      clear: ["clear"],
      cls: ["clear"],
    };
  }

  setupEventListeners() {
    this.consoleInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        const input = this.consoleInput.value.trim();
        if (input) {
          this.processCommand(input);
          this.consoleInput.value = "";
        }
      }
    });

    // Focus no input quando clicar no console
    this.consoleBody.addEventListener("click", () => {
      this.consoleInput.focus();
    });
  }

  processCommand(input) {
    // Adiciona o comando do usuário
    this.addLine(`você@terminal:~$ ${input}`, "user");

    // Processa o comando
    const command = input.toLowerCase();
    let response = this.findResponse(command);

    if (command === "clear" || command === "cls") {
      this.clearConsole();
      return;
    }

    if (!response) {
      response = [
        `Comando '${input}' não reconhecido.`,
        "Digite 'help' para ver os comandos disponíveis.",
      ];
    }

    // Adiciona a resposta com delay para simular processamento
    setTimeout(() => {
      response.forEach((line, index) => {
        setTimeout(() => {
          this.addLine(`assistant@ruts:~$ ${line}`, "assistant");
        }, index * 300);
      });
    }, 500);
  }

  findResponse(command) {
    // Busca exata
    if (this.responses[command]) {
      return this.responses[command];
    }

    // Busca por palavras-chave
    const keywords = {
      experiência: "experiencia",
      experiencia: "experiencia",
      habilidades: "skills",
      tecnologias: "skills",
      email: "contato",
      telefone: "contato",
      linkedin: "contato",
      github: "contato",
      javascript: "frontend",
      react: "frontend",
      html: "frontend",
      css: "frontend",
      jquery: "frontend",
      node: "backend",
      nodejs: "backend",
      python: "backend",
      php: "backend",
      docker: "devops",
      kubernetes: "devops",
      aws: "devops",
      infraestrutura: "devops",
      redes: "devops",
      virtualização: "devops",
      virtualizacao: "devops",
      hospedagem: "devops",
      quem: "sobre",
      você: "sobre",
      voce: "sobre",
    };

    for (const [keyword, responseKey] of Object.entries(keywords)) {
      if (command.includes(keyword)) {
        return this.responses[responseKey];
      }
    }

    // Respostas para perguntas comuns
    if (command.includes("como") && command.includes("contato")) {
      return this.responses["contato"];
    }

    if (
      command.includes("qual") &&
      (command.includes("experiencia") || command.includes("experiência"))
    ) {
      return this.responses["experiencia"];
    }

    if (command.includes("que") && command.includes("tecnologia")) {
      return this.responses["skills"];
    }

    return null;
  }

  addLine(text, type) {
    const line = document.createElement("div");
    line.className = "console-line";

    const prompt = document.createElement("span");
    prompt.className = "console-prompt";

    const textSpan = document.createElement("span");
    textSpan.className = "console-text";

    if (type === "user") {
      prompt.textContent = "você@terminal:~$";
      textSpan.textContent = text.replace("você@terminal:~$ ", "");
    } else {
      prompt.textContent = "assistant@ruts:~$";
      textSpan.textContent = text.replace("assistant@ruts:~$ ", "");
    }

    line.appendChild(prompt);
    line.appendChild(textSpan);

    this.consoleBody.appendChild(line);
    this.consoleBody.scrollTop = this.consoleBody.scrollHeight;
  }

  clearConsole() {
    this.consoleBody.innerHTML = `
            <div class="console-line">
                <span class="console-prompt">assistant@ruts:~$</span>
                <span class="console-text">Terminal limpo! Digite 'help' para ver os comandos.</span>
            </div>
        `;
  }
}

// Initialize console when page loads
document.addEventListener("DOMContentLoaded", () => {
  new ConsoleAssistant();
});

// Active nav link highlighting
window.addEventListener("scroll", () => {
  const sections = document.querySelectorAll("section[id]");
  const navLinks = document.querySelectorAll('.nav-menu a[href^="#"]');

  let current = "";

  sections.forEach((section) => {
    const sectionTop = section.offsetTop;
    const sectionHeight = section.clientHeight;
    if (scrollY >= sectionTop - 200) {
      current = section.getAttribute("id");
    }
  });

  navLinks.forEach((link) => {
    link.classList.remove("active");
    if (link.getAttribute("href") === `#${current}`) {
      link.classList.add("active");
    }
  });
});

// Form submission
document.querySelector(".contact-form form").addEventListener("submit", (e) => {
  e.preventDefault();

  // Get form data
  const formData = new FormData(e.target);
  const data = Object.fromEntries(formData);

  // Simple form validation
  if (!data.nome || !data.email || !data.mensagem) {
    alert("Por favor, preencha todos os campos.");
    return;
  }

  // Simulate form submission
  const button = e.target.querySelector("button");
  const originalText = button.textContent;

  button.textContent = "Enviando...";
  button.disabled = true;

  setTimeout(() => {
    alert("Mensagem enviada com sucesso! Entrarei em contato em breve.");
    e.target.reset();
    button.textContent = originalText;
    button.disabled = false;
  }, 2000);
});

// Intersection Observer for animations
const observerOptions = {
  threshold: 0.1,
  rootMargin: "0px 0px -50px 0px",
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.style.animation = "fadeIn 0.6s ease forwards";
    }
  });
}, observerOptions);

// Observe elements for animation
document.addEventListener("DOMContentLoaded", () => {
  const elementsToAnimate = document.querySelectorAll(
    ".skill-category, .project-card, .stat"
  );
  elementsToAnimate.forEach((el) => {
    el.style.opacity = "0";
    observer.observe(el);
  });
});

// Typing effect for hero section
function typeWriter(element, text, speed = 50) {
  let i = 0;
  element.textContent = "";

  function type() {
    if (i < text.length) {
      element.textContent += text.charAt(i);
      i++;
      setTimeout(type, speed);
    }
  }

  type();
}

// Easter eggs for console
document.addEventListener("keydown", (e) => {
  // Konami Code easter egg
  const konamiCode = [38, 38, 40, 40, 37, 39, 37, 39, 66, 65]; // ↑↑↓↓←→←→BA
  window.konamiIndex = window.konamiIndex || 0;

  if (e.keyCode === konamiCode[window.konamiIndex]) {
    window.konamiIndex++;
    if (window.konamiIndex === konamiCode.length) {
      console.log("🎮 Konami Code activated! You found the easter egg!");
      document.body.style.animation = "rainbow 2s linear infinite";
      setTimeout(() => {
        document.body.style.animation = "";
      }, 10000);
      window.konamiIndex = 0;
    }
  } else {
    window.konamiIndex = 0;
  }
});

// Add rainbow animation for easter egg
const style = document.createElement("style");
style.textContent = `
    @keyframes rainbow {
        0% { filter: hue-rotate(0deg); }
        100% { filter: hue-rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Particle effect for hero section (optional enhancement)
class ParticleSystem {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.particles = [];
    this.init();
    this.animate();
  }

  init() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;

    for (let i = 0; i < 50; i++) {
      this.particles.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        size: Math.random() * 2 + 1,
        opacity: Math.random() * 0.5 + 0.2,
      });
    }
  }

  animate() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    this.particles.forEach((particle) => {
      particle.x += particle.vx;
      particle.y += particle.vy;

      if (particle.x < 0 || particle.x > this.canvas.width) particle.vx *= -1;
      if (particle.y < 0 || particle.y > this.canvas.height) particle.vy *= -1;

      this.ctx.beginPath();
      this.ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
      this.ctx.fillStyle = `rgba(0, 255, 136, ${particle.opacity})`;
      this.ctx.fill();
    });

    requestAnimationFrame(() => this.animate());
  }
}

// Initialize particle system if canvas exists
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.querySelector("#particles");
  if (canvas) {
    new ParticleSystem(canvas);
  }
});

// Performance optimization: Lazy loading for images
if ("IntersectionObserver" in window) {
  const imageObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const img = entry.target;
        img.src = img.dataset.src;
        img.classList.remove("lazy");
        imageObserver.unobserve(img);
      }
    });
  });

  document.querySelectorAll("img[data-src]").forEach((img) => {
    imageObserver.observe(img);
  });
}
