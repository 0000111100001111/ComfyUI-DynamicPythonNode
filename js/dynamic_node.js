import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Comfy.DynamicRuntimeNode",

    async setup() {
        api.addEventListener("dynamic_node_error", ({ detail }) => {
            const { error } = detail;
            alert(`Dynamic Node Error:\n\n${error}`);
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "DynamicRuntimeNode") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onNodeCreated?.apply(this, arguments);

                const codeWidget = this.widgets.find(w => w.name === "code");

                this.updateButtonStatus = (isOk) => {
                    if (this.compileBtn) {
                        this.compileBtn.name = isOk ? "Compiled" : "Verify and compile code";
                        this.compileBtn.color = isOk ? "#242" : "#722"; 
                        if (this.compileBtn.options) this.compileBtn.options.color = isOk ? "#242" : "#722";
                        this.setDirtyCanvas(true);
                    }
                };

                // Create the compile button
                if (!this.compileBtn) {
                    this.compileBtn = this.addWidget("button", "Verify and compile code", null, () => {
                        api.fetchApi("/dynamic_node/compile", {
                            method: "POST",
                            body: JSON.stringify({ code: codeWidget.value })
                        }).then(async response => {
                            const data = await response.json();
                            if (!response.ok) {
                                this.updateButtonStatus(false);
                                alert(`Syntax error\n\n${data.error}`);
                                return;
                            }

                            this.updateButtonStatus(true);

                            const oldInputs = this.inputs ? this.inputs.map((input) => {
                                const link = this.graph.links[input.link];
                                return { name: input.name, type: input.type, origin_id: link ? link.origin_id : null, origin_slot: link ? link.origin_slot : null };
                            }).filter(i => i.name !== "code") : [];

                            const oldOutputs = this.outputs ? this.outputs.map((output) => {
                                const connections = [];
                                if (output.links) {
                                    output.links.forEach(linkId => {
                                        const link = this.graph.links[linkId];
                                        if (link) connections.push({ target_id: link.target_id, target_slot: link.target_slot });
                                    });
                                }
                                return { name: output.name, type: output.type, connections };
                            }) : [];

                            // Remove all current outputs
                            if (this.inputs) {
                                for (let i = this.inputs.length - 1; i >= 0; i--) {
                                    if (this.inputs[i].name !== "code") this.removeInput(i);
                                }
                            }
                            if (this.outputs) {
                                while (this.outputs.length > 0) this.removeOutput(0);
                                this.outputs = []; // Force empty array
                            }

                            data.inputs.forEach(input => {
                                this.addInput(input.name, input.type);
                                const backup = oldInputs.find(old => old.name === input.name);
                                if (backup && backup.origin_id !== null) {
                                    const originNode = this.graph.getNodeById(backup.origin_id);
                                    if (originNode) originNode.connect(backup.origin_slot, this, input.name);
                                }
                            });

                            data.outputs.forEach((output, index) => {
                                this.addOutput(output.name, output.type);
                                const backup = oldOutputs.find(old => old.name === output.name);
                                if (backup && backup.connections.length > 0) {
                                    backup.connections.forEach(conn => {
                                        const targetNode = this.graph.getNodeById(conn.target_id);
                                        if (targetNode) this.connect(index, targetNode, conn.target_slot);
                                    });
                                }
                            });

                            const currentSize = [this.size[0], this.size[1]];
                            const requiredSize = this.computeSize();
                            this.setSize([Math.max(currentSize[0], requiredSize[0]), Math.max(currentSize[1], requiredSize[1])]);

                            this.graph.runStep();
                            this.setDirtyCanvas(true, true);
                        });
                    });

                    // Move the button back to the top
                    const btnIdx = this.widgets.indexOf(this.compileBtn);
                    if (btnIdx !== -1 && btnIdx !== 0) {
                        this.widgets.splice(btnIdx, 1);
                        this.widgets.unshift(this.compileBtn);
                    }
                }

                this.updateButtonStatus(false);
                const node = this;

                if (codeWidget) {
                    let lastValue = codeWidget.value;
                    const originalCallback = codeWidget.callback;
                    codeWidget.callback = function(value) {
                        if (value !== lastValue) {
                            lastValue = value;
                            node.updateButtonStatus(false);
                        }
                        if (originalCallback) return originalCallback.apply(this, arguments);
                    };
                }
            };
        }
    }
});
