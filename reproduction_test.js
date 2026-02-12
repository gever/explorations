
// Mocking necessary parts of bwxBASIC for reproduction

const Tokenizer = {
    // Added ^ to the operator group
    regex: /([0-9]*\.?[0-9]+)|(".*?")|([a-zA-Z][a-zA-Z0-9_]*\$?)|(<=|>=|<>|<|>|=)|([\+\-\*\/\^])|(\()|(\))|(:)|(,)|(;)|(')/g,
    tokenize: (str) => { const t = []; let m; while ((m = Tokenizer.regex.exec(str)) !== null) t.push(m[0]); return t; }
};

const LIB = {
    'SIN': 'Math.sin', 'COS': 'Math.cos', 'TAN': 'Math.tan', 'ATN': 'Math.atan', 'EXP': 'Math.exp', 'LOG': 'Math.log', 'SQR': 'Math.sqrt', 'ABS': 'Math.abs',
    'INT': 'Math.floor', 'RND': 'SYS.rnd', 'RAND': 'SYS.rnd',
    'LEN': '(s)=>(s+"").length', 'LEFT$': '(s,n)=>(s+"").substr(0,n)', 'RIGHT$': '(s,n)=>(s+"").substr((s+"").length-n)', 'MID$': '(s,st,ln)=>(s+"").substr(st-1,ln)',
    'STR$': '(n)=>n.toString()', 'VAL': '(s)=>parseFloat(s)'
};

const SYS = { vars: { A: 5, B: 3 }, getArray: () => 0 };

const Compiler = {
    genExpression: (tokens, ctx) => {
        const peek = () => tokens[ctx.idx], next = () => tokens[ctx.idx++];
        const parseExp = () => { let l = parseTerm(); while (ctx.idx < tokens.length && (peek() === '+' || peek() === '-')) l = `(${l} ${next()} ${parseTerm()})`; if (ctx.idx < tokens.length && ['=', '<', '>', '<=', '>=', '<>'].includes(peek())) { let op = next(), jop = op === '=' ? '===' : op === '<>' ? '!==' : op; l = `(${l} ${jop} ${parseExp()}?1:0)`; } return l; };

        // Modified parseTerm to call parsePower instead of parseFactor
        const parseTerm = () => { let l = parsePower(); while (ctx.idx < tokens.length && (peek() === '*' || peek() === '/')) l = `(${l} ${next()} ${parsePower()})`; return l; };

        // Added parsePower
        const parsePower = () => {
            let l = parseFactor();
            while (ctx.idx < tokens.length && peek() === '^') {
                next(); // consume ^
                // TODO: Fix operator precedence for power operator vs unary minus (currently -2^2=4, should be -4)
                l = `Math.pow(${l}, ${parseFactor()})`;
            }
            return l;
        };

        const parseFactor = () => {
            const t = next();
            if (!t) return "0";
            if (!isNaN(t) || t.startsWith('"')) return t;
            if (t === '(') { const e = parseExp(); next(); return `(${e})`; }
            if (t === '-') return `-${parseFactor()}`;
            if (t === '+') return parseFactor();

            if (/^[a-zA-Z]/.test(t)) {
                // Normalize token for Keyword/Function checks
                const tu = t.toUpperCase();

                // Handle Math Functions (SIN, LEN, etc)
                if (LIB[tu]) {
                    next(); const a = [];
                    if (peek() !== ')') do { a.push(parseExp()); if (peek() === ',') next(); else break; } while (true);
                    next(); return `(${LIB[tu]})(${a.join(',')})`;
                }

                return `(SYS.vars['${t}']!==undefined?SYS.vars['${t}']:0)`;
            }
            return "0"; // Should fallback/error but for now 0
        };
        return parseExp();
    },
    compile: (src) => {
        const tokens = Tokenizer.tokenize(src);
        console.log("Tokens:", tokens);
        const ctx = { idx: 0 };
        return Compiler.genExpression(tokens, ctx);
    }
};

try {
    const expr = "IF (A ^ B) <> 125";
    console.log("Compiling:", expr);
    // Simulation
    const tokens = Tokenizer.tokenize("(A ^ B)");
    console.log("Tokens for (A ^ B):", tokens);

    const js = Compiler.compile("(A ^ B)");
    console.log("Generated JS:", js);

    // Evaluate it to see if it matches expectations (A=5, B=3 -> 125)
    // We can't easily eval without full context but inspecting the string is enough
} catch (e) {
    console.error("Error:", e);
}
