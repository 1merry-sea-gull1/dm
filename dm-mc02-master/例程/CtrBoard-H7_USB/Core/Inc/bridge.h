#ifndef BRIDGE_H
#define BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

void Bridge_Init(void);
void Bridge_Process(void);
void Bridge_UsbReceive(const uint8_t *data, uint32_t length);
void Bridge_UsbTxComplete(void);

#ifdef __cplusplus
}
#endif

#endif /* BRIDGE_H */
