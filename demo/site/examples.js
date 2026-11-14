'use strict';

// Explicitly illustrative teaching examples. They are not measured case results.
window.IdeaXExamples = {
  render(id) {
    const frame=(title,body,note)=>`<section class="teaching-example" aria-label="Interactive teaching example"><p class="eyebrow">TRY A SMALL EXAMPLE · ILLUSTRATIVE ONLY</p><h4>${title}</h4>${body}<p class="example-caveat">${note}</p></section>`;
    if(id==='compression')return frame('Same model budget. Different choices.',
      '<p>Keep exactly two of four connections. A kept weight can use either neighboring tenth. Change the choices to see the resulting candidate.</p><div class="weight-grid" aria-label="Four example connections"></div><div class="example-controls"><label><input type="checkbox" id="toy-mask"> Swap connection 1 for connection 2</label><label><input type="checkbox" id="toy-round"> Round connection 3 up</label></div><p class="example-result" aria-live="polite" id="toy-result"></p>',
      'Decimal tenths simplify the example; they are not a real FP4 format. No task scores are invented. The research must test whether these choices help.');
    if(id==='residency')return frame('A draft needs A, B, and C. Only two fit afterward.',
      '<p>All three experts must be served during verification, using loading or waiting when needed. Click to reveal what happened to the draft.</p><div class="expert-grid"><div data-expert="A"><b>Expert A</b><span>Needed for the check</span></div><div data-expert="B"><b>Expert B</b><span>Needed for the check</span></div><div data-expert="C"><b>Expert C</b><span>Needed for the check</span></div></div><button class="button small" id="toy-outcome" aria-pressed="false">Reveal the draft outcome →</button><p class="example-result" aria-live="polite" id="toy-result">Execution now: A + B + C. Retention later: still undecided.</p>',
      'A/B/C are illustrative expert labels. Being used by rejected tokens does not prove that an expert will be useless later; that predictive value is the hypothesis to test.');
    if(id==='attribution')return frame('Change one factor at a time.',
      '<p>Each box represents a replay with the same input. Select a comparison to see what it isolates.</p><div class="factor-grid"><button data-factor="00" class="selected">Old weights<br>Old scale</button><button data-factor="10">New weights<br>Old scale</button><button data-factor="01">Old weights<br>New scale</button><button data-factor="11">New weights<br>New scale</button></div><p class="example-result" aria-live="polite" id="toy-result">Start with the old/old reference. Measure its output, then compare the other boxes.</p>',
      'This is an experimental design, not a reported result. Scale dominance is one possibility, not an assumption.');
    if(id==='verification')return frame('A safe range can make a decision clear.',
      '<p>Suppose valid bounds put the acceptance threshold between <strong>0.6 and 0.8</strong>. Move the same random draw used by the reference check.</p><label class="example-range" for="toy-draw">Random draw U <output id="toy-draw-value">0.40</output></label><input id="toy-draw" type="range" min="0" max="1" step="0.01" value="0.4"><div class="bound-bar"><span id="toy-marker"></span><i>Accept</i><i>Refine</i><i>Reject</i></div><p class="example-result" aria-live="polite" id="toy-result"></p>',
      'The interval is illustrative and assumed valid. Constructing cheap valid bounds, handling rejection sampling, and maintaining future state are the difficult research tasks.');
    if(id==='replay')return frame('Why an occasional accurate step is not enough.',
      '<p>For one hypothetical gradient coordinate, let the cheap estimate be 8 and the reference be 10. A correction happens with probability 1 in 4.</p><div class="example-controls"><label><input type="checkbox" id="toy-correction"> Apply the weighted residual correction</label></div><div class="replay-grid"><div><small>3/4 of the time</small><b id="toy-common">8</b></div><div><small>1/4 of the time</small><b id="toy-rare">10</b></div><div><small>Expected value</small><b id="toy-mean">8.5</b></div></div><p class="example-result" aria-live="polite" id="toy-result"></p>',
      'This scalar example explains an established estimator identity. A correct mean does not guarantee stable training, low variance, or identical adaptive-optimizer behavior.');
    return frame('A small turn does not cap the amplifier.',
      '<p>Imagine an amplifier at gain 1.0. Each turn is small, but several upward turns can accumulate. This is only an analogy for weight-matrix gain.</p><div class="gain-display"><span>Illustrative gain</span><b id="toy-gain">1.0×</b></div><div class="example-controls"><button class="button small" id="toy-step">Add a small +0.1 turn</button><button class="button small" id="toy-normalize">Rescale to 1.0</button></div><p class="example-result" aria-live="polite" id="toy-result">A step-size limit and an overall-gain constraint answer different questions.</p>',
      'Real matrix updates are not scalar knob turns. The proposal studies direction choice under a matrix constraint; this illustration does not predict a training benefit.');
  },
  bind(id,pause) {
    const q=(s)=>document.querySelector(s);
    const on=(s,event,fn)=>q(s)?.addEventListener(event,()=>{pause();fn();});
    const result=(s)=>q('#toy-result').textContent=s;
    if(id==='compression') {
      const update=()=>{
        const swap=q('#toy-mask').checked,round=q('#toy-round').checked;
        const values=[swap?'removed':'0.3',swap?'0.6':'removed',round?'0.5':'0.4','removed'];
        q('.weight-grid').innerHTML=['0.34','0.62','0.47','0.83'].map((n,i)=>`<div class="${values[i]==='removed'?'removed':'kept'}"><small>Connection ${i+1}</small><span>${n}</span><span aria-hidden="true">↓</span><b>${values[i]}</b></div>`).join('');
        result('Candidate: two active connections, same allowed number set. Next, run this candidate on task examples and measure the error.');
      };on('#toy-mask','change',update);on('#toy-round','change',update);update();
    } else if(id==='residency')on('#toy-outcome','click',()=>{
      const reveal=q('#toy-outcome').getAttribute('aria-pressed')!=='true';
      q('#toy-outcome').setAttribute('aria-pressed',String(reveal));
      q('#toy-outcome').textContent=reveal?'Reset the example ↺':'Reveal the draft outcome →';
      for(const name of ['A','B','C']) {
        const el=q(`[data-expert=${name}]`);
        el.classList.toggle('rejected',reveal&&name==='C');
        el.querySelector('span').textContent=!reveal?'Needed for the check':name==='C'?'Used only by rejected tokens':'Used by accepted tokens';
      }
      result(reveal?'A and B served accepted tokens; C served only rejected tokens. All three still had to execute. Now ask whether this information helps decide which two to keep.':'Execution now: A + B + C. Retention later: still undecided.');
    });
    else if(id==='attribution')document.querySelectorAll('[data-factor]').forEach(b=>b.addEventListener('click',()=>{
      pause();document.querySelectorAll('[data-factor]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});
      result({'00':'Reference: both factors use their old values. This anchors the other comparisons.','10':'Only weights changed. Compare with old/old to measure the weight effect at the old scale.','01':'Only scale changed. Compare with old/old to measure the scale effect at the old weights.','11':'Both changed. Compare all four results to see whether the combined effect differs from the sum of the separate effects.'}[b.dataset.factor]);
    }));
    else if(id==='verification') {
      const update=()=>{const u=Number(q('#toy-draw').value);q('#toy-draw-value').textContent=u.toFixed(2);q('#toy-marker').style.left=`${u*100}%`;
        result(u<=.6?'Accept: even the lowest possible threshold accepts this draw.':u>.8?'Reject: even the highest possible threshold rejects this draw.':'Refine: possible thresholds disagree. Use a tighter bound or the reference calculation.');};
      on('#toy-draw','input',update);update();
    } else if(id==='replay') {
      const update=()=>{const corrected=q('#toy-correction').checked;q('#toy-rare').textContent=corrected?'16':'10';q('#toy-mean').textContent=corrected?'10':'8.5';
        result(corrected?'On a correction step: 8 + (10 − 8) / 0.25 = 16. The expectation is 0.75 × 8 + 0.25 × 16 = 10, but the individual updates are noisier.':'Simply using 10 one quarter of the time gives 0.75 × 8 + 0.25 × 10 = 8.5. Occasional accurate steps do not remove the bias.');};
      on('#toy-correction','change',update);update();
    } else {
      let gain=1;
      on('#toy-step','click',()=>{gain+=.1;q('#toy-gain').textContent=gain.toFixed(1)+'×';result('Each turn was only 0.1, but the total gain is now '+gain.toFixed(1)+'. Limiting a change does not bound the accumulated state.');});
      on('#toy-normalize','click',()=>{gain=1;q('#toy-gain').textContent='1.0×';result('Rescaling controls the final gain. The research asks whether choosing a constraint-aware matrix direction first helps more than this after-the-fact correction.');});
    }
  }
};
