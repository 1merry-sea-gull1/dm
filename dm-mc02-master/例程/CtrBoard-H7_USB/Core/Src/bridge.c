/*
 * Minimal DM-MC02 USB CDC <-> FDCAN bridge.
 *
 * The bridge is intentionally independent from the wheel-legged control
 * firmware. It only forwards raw classic CAN frames and never enables or
 * commands a motor by itself.
 */

#include "bridge.h"
#include "usbd_cdc_if.h"

#include <string.h>

#define BRIDGE_VERSION          1U
#define BRIDGE_MAGIC_0          0xA5U
#define BRIDGE_MAGIC_1          0x5AU
#define BRIDGE_MAX_PAYLOAD      512U
#define BRIDGE_HEADER_SIZE      8U
#define BRIDGE_MAX_FRAME        (BRIDGE_HEADER_SIZE + BRIDGE_MAX_PAYLOAD + 2U)

#define BRIDGE_CMD_PING             0x01U
#define BRIDGE_CMD_ACK              0x03U
#define BRIDGE_CMD_NACK             0x04U
#define BRIDGE_CMD_CAN_TX           0x10U
#define BRIDGE_CMD_CAN_RX           0x11U
#define BRIDGE_CMD_STREAM_START     0x12U
#define BRIDGE_CMD_STREAM_STOP      0x13U

#define USB_RX_RING_SIZE        4096U
#define USB_TX_QUEUE_DEPTH      48U
#define USB_TX_PACKET_SIZE      64U
#define CAN_EVENT_QUEUE_DEPTH   64U

#define CAN_PAYLOAD_SIZE        19U

typedef struct
{
  uint16_t length;
  uint8_t data[USB_TX_PACKET_SIZE];
} UsbTxPacket;

typedef struct
{
  uint8_t bus;
  uint32_t id;
  uint8_t flags;
  uint8_t length;
  uint8_t data[8];
  uint32_t timestamp;
} CanEvent;

FDCAN_HandleTypeDef hfdcan1;
FDCAN_HandleTypeDef hfdcan2;

static volatile uint16_t usb_rx_head;
static volatile uint16_t usb_rx_tail;
static uint8_t usb_rx_ring[USB_RX_RING_SIZE];

static UsbTxPacket usb_tx_queue[USB_TX_QUEUE_DEPTH];
static uint16_t usb_tx_head;
static uint16_t usb_tx_tail;
static uint8_t usb_tx_packet[USB_TX_PACKET_SIZE];
static uint16_t usb_tx_length;
static uint8_t usb_tx_pending;
static volatile uint8_t usb_tx_busy;

static volatile uint16_t can_event_head;
static volatile uint16_t can_event_tail;
static CanEvent can_event_queue[CAN_EVENT_QUEUE_DEPTH];

static uint8_t protocol_buffer[BRIDGE_MAX_FRAME];
static uint16_t protocol_length;
static volatile uint8_t can_streaming;
static uint8_t can_ready;
static uint16_t tx_sequence;

static uint16_t CRC16(const uint8_t *data, uint16_t length)
{
  uint16_t crc = 0xFFFFU;
  uint16_t i;
  uint8_t bit;

  for (i = 0U; i < length; i++)
  {
    crc ^= (uint16_t)((uint16_t)data[i] << 8);
    for (bit = 0U; bit < 8U; bit++)
    {
      if ((crc & 0x8000U) != 0U)
      {
        crc = (uint16_t)((crc << 1) ^ 0x1021U);
      }
      else
      {
        crc = (uint16_t)(crc << 1);
      }
    }
  }
  return crc;
}

static uint8_t UsbQueueFrame(uint8_t command, const uint8_t *payload,
                             uint16_t length, uint16_t sequence)
{
  UsbTxPacket *packet;
  uint16_t next;
  uint16_t crc;

  if ((length > (USB_TX_PACKET_SIZE - (BRIDGE_HEADER_SIZE + 2U))) ||
      (length > BRIDGE_MAX_PAYLOAD))
  {
    return 0U;
  }

  next = (uint16_t)((usb_tx_head + 1U) % USB_TX_QUEUE_DEPTH);
  if (next == usb_tx_tail)
  {
    return 0U;
  }

  packet = &usb_tx_queue[usb_tx_head];
  packet->data[0] = BRIDGE_MAGIC_0;
  packet->data[1] = BRIDGE_MAGIC_1;
  packet->data[2] = BRIDGE_VERSION;
  packet->data[3] = command;
  packet->data[4] = (uint8_t)(sequence & 0xFFU);
  packet->data[5] = (uint8_t)((sequence >> 8) & 0xFFU);
  packet->data[6] = (uint8_t)(length & 0xFFU);
  packet->data[7] = (uint8_t)((length >> 8) & 0xFFU);

  if ((payload != NULL) && (length > 0U))
  {
    memcpy(&packet->data[BRIDGE_HEADER_SIZE], payload, length);
  }

  crc = CRC16(&packet->data[2], (uint16_t)(6U + length));
  packet->data[BRIDGE_HEADER_SIZE + length] = (uint8_t)(crc & 0xFFU);
  packet->data[BRIDGE_HEADER_SIZE + length + 1U] = (uint8_t)((crc >> 8) & 0xFFU);
  packet->length = (uint16_t)(BRIDGE_HEADER_SIZE + length + 2U);

  usb_tx_head = next;
  return 1U;
}

static void UsbQueueAck(uint8_t command, uint16_t sequence)
{
  (void)UsbQueueFrame(command, NULL, 0U, sequence);
}

static void CanEventPush(uint8_t bus, const FDCAN_RxHeaderTypeDef *header,
                         const uint8_t *data)
{
  CanEvent *event;
  uint16_t next;
  uint8_t length;
  uint32_t primask;

  /* This HAL version exposes the raw DLC code in DataLength (0..8). */
  length = (uint8_t)(header->DataLength & 0x0FU);
  if (length > 8U)
  {
    length = 8U;
  }

  primask = __get_PRIMASK();
  __disable_irq();

  next = (uint16_t)((can_event_head + 1U) % CAN_EVENT_QUEUE_DEPTH);
  if (next != can_event_tail)
  {
    event = &can_event_queue[can_event_head];
    event->bus = bus;
    event->id = header->Identifier;
    event->flags = (header->IdType == FDCAN_EXTENDED_ID) ? 1U : 0U;
    event->length = length;
    memset(event->data, 0, sizeof(event->data));
    if (length > 0U)
    {
      memcpy(event->data, data, length);
    }
    event->timestamp = HAL_GetTick();
    can_event_head = next;
  }

  __set_PRIMASK(primask);
}

static uint8_t CanSend(uint8_t bus, uint32_t id, uint8_t flags,
                       const uint8_t *data, uint8_t length)
{
  FDCAN_TxHeaderTypeDef tx_header;
  FDCAN_HandleTypeDef *hcan;

  if ((length > 8U) || ((bus != 0U) && (bus != 1U)))
  {
    return 0U;
  }

  hcan = (bus == 0U) ? &hfdcan1 : &hfdcan2;

  memset(&tx_header, 0, sizeof(tx_header));
  tx_header.Identifier = id;
  tx_header.IdType = ((flags & 1U) != 0U) ? FDCAN_EXTENDED_ID : FDCAN_STANDARD_ID;
  tx_header.TxFrameType = FDCAN_DATA_FRAME;
  tx_header.DataLength = (uint32_t)length;
  tx_header.ErrorStateIndicator = FDCAN_ESI_ACTIVE;
  tx_header.BitRateSwitch = FDCAN_BRS_OFF;
  tx_header.FDFormat = FDCAN_CLASSIC_CAN;
  tx_header.TxEventFifoControl = FDCAN_NO_TX_EVENTS;
  tx_header.MessageMarker = 0U;

  return (HAL_FDCAN_AddMessageToTxFifoQ(hcan, &tx_header, (uint8_t *)data) == HAL_OK)
             ? 1U
             : 0U;
}

static void ProcessProtocolFrame(const uint8_t *frame, uint16_t total_length)
{
  uint8_t command = frame[3];
  uint16_t sequence = (uint16_t)frame[4] | ((uint16_t)frame[5] << 8);
  uint16_t payload_length = (uint16_t)frame[6] | ((uint16_t)frame[7] << 8);
  const uint8_t *payload = &frame[BRIDGE_HEADER_SIZE];
  uint8_t result;

  (void)total_length;

  switch (command)
  {
    case BRIDGE_CMD_PING:
      (void)UsbQueueFrame(BRIDGE_CMD_ACK, (const uint8_t *)"DM-MC02-BRIDGE",
                          sizeof("DM-MC02-BRIDGE") - 1U, sequence);
      break;

    case BRIDGE_CMD_STREAM_START:
      can_streaming = 1U;
      UsbQueueAck(BRIDGE_CMD_ACK, sequence);
      break;

    case BRIDGE_CMD_STREAM_STOP:
      can_streaming = 0U;
      UsbQueueAck(BRIDGE_CMD_ACK, sequence);
      break;

    case BRIDGE_CMD_CAN_TX:
      if ((payload_length < CAN_PAYLOAD_SIZE) || (can_ready == 0U))
      {
        UsbQueueAck(BRIDGE_CMD_NACK, sequence);
        break;
      }

      result = CanSend(payload[0],
                       (uint32_t)payload[1] |
                           ((uint32_t)payload[2] << 8) |
                           ((uint32_t)payload[3] << 16) |
                           ((uint32_t)payload[4] << 24),
                       payload[5],
                       &payload[7],
                       payload[6]);

      UsbQueueAck(result != 0U ? BRIDGE_CMD_ACK : BRIDGE_CMD_NACK, sequence);
      break;

    default:
      UsbQueueAck(BRIDGE_CMD_NACK, sequence);
      break;
  }
}

static void ProtocolFeedByte(uint8_t byte)
{
  uint16_t payload_length;
  uint16_t total_length;
  uint16_t received_crc;
  uint16_t calculated_crc;

  if (protocol_length == 0U)
  {
    if (byte == BRIDGE_MAGIC_0)
    {
      protocol_buffer[protocol_length++] = byte;
    }
    return;
  }

  if (protocol_length == 1U)
  {
    if (byte == BRIDGE_MAGIC_1)
    {
      protocol_buffer[protocol_length++] = byte;
    }
    else
    {
      protocol_length = 0U;
      if (byte == BRIDGE_MAGIC_0)
      {
        protocol_buffer[protocol_length++] = byte;
      }
    }
    return;
  }

  if (protocol_length >= sizeof(protocol_buffer))
  {
    protocol_length = 0U;
    return;
  }

  protocol_buffer[protocol_length++] = byte;

  if (protocol_length < BRIDGE_HEADER_SIZE)
  {
    return;
  }

  if (protocol_buffer[2] != BRIDGE_VERSION)
  {
    protocol_length = 0U;
    return;
  }

  payload_length = (uint16_t)protocol_buffer[6] |
                   ((uint16_t)protocol_buffer[7] << 8);
  if (payload_length > BRIDGE_MAX_PAYLOAD)
  {
    protocol_length = 0U;
    return;
  }

  total_length = (uint16_t)(BRIDGE_HEADER_SIZE + payload_length + 2U);
  if (protocol_length < total_length)
  {
    return;
  }

  received_crc = (uint16_t)protocol_buffer[BRIDGE_HEADER_SIZE + payload_length] |
                 ((uint16_t)protocol_buffer[BRIDGE_HEADER_SIZE + payload_length + 1U] << 8);
  calculated_crc = CRC16(&protocol_buffer[2], (uint16_t)(6U + payload_length));

  if (received_crc == calculated_crc)
  {
    ProcessProtocolFrame(protocol_buffer, total_length);
  }

  protocol_length = 0U;
}

static void UsbTxPump(void)
{
  uint8_t result;

  if (usb_tx_busy != 0U)
  {
    return;
  }

  if (usb_tx_pending == 0U)
  {
    if (usb_tx_tail == usb_tx_head)
    {
      return;
    }

    usb_tx_length = usb_tx_queue[usb_tx_tail].length;
    memcpy(usb_tx_packet, usb_tx_queue[usb_tx_tail].data, usb_tx_length);
    usb_tx_tail = (uint16_t)((usb_tx_tail + 1U) % USB_TX_QUEUE_DEPTH);
    usb_tx_pending = 1U;
  }

  result = CDC_Transmit_HS(usb_tx_packet, usb_tx_length);
  if (result == USBD_OK)
  {
    usb_tx_pending = 0U;
    usb_tx_busy = 1U;
  }
  else if (result != USBD_BUSY)
  {
    usb_tx_pending = 0U;
  }
}

static uint8_t CanInit(void)
{
  GPIO_InitTypeDef gpio = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};
  FDCAN_FilterTypeDef filter = {0};

  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio.Alternate = GPIO_AF9_FDCAN1;
  HAL_GPIO_Init(GPIOD, &gpio);

  gpio.Pin = GPIO_PIN_5 | GPIO_PIN_6;
  gpio.Alternate = GPIO_AF9_FDCAN2;
  HAL_GPIO_Init(GPIOB, &gpio);

  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_FDCAN;
  peripheral_clock.FdcanClockSelection = RCC_FDCANCLKSOURCE_PLL;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK)
  {
    return 0U;
  }

  __HAL_RCC_FDCAN_CLK_ENABLE();

  hfdcan1.Instance = FDCAN1;
  hfdcan1.Init.FrameFormat = FDCAN_FRAME_CLASSIC;
  hfdcan1.Init.Mode = FDCAN_MODE_NORMAL;
  hfdcan1.Init.AutoRetransmission = ENABLE;
  hfdcan1.Init.TransmitPause = DISABLE;
  hfdcan1.Init.ProtocolException = DISABLE;
  hfdcan1.Init.NominalPrescaler = 6U;
  hfdcan1.Init.NominalSyncJumpWidth = 1U;
  hfdcan1.Init.NominalTimeSeg1 = 14U;
  hfdcan1.Init.NominalTimeSeg2 = 5U;
  hfdcan1.Init.DataPrescaler = 6U;
  hfdcan1.Init.DataSyncJumpWidth = 1U;
  hfdcan1.Init.DataTimeSeg1 = 14U;
  hfdcan1.Init.DataTimeSeg2 = 5U;
  hfdcan1.Init.MessageRAMOffset = 0U;
  hfdcan1.Init.StdFiltersNbr = 1U;
  hfdcan1.Init.ExtFiltersNbr = 1U;
  hfdcan1.Init.RxFifo0ElmtsNbr = 16U;
  hfdcan1.Init.RxFifo0ElmtSize = FDCAN_DATA_BYTES_8;
  hfdcan1.Init.RxFifo1ElmtsNbr = 0U;
  hfdcan1.Init.RxFifo1ElmtSize = FDCAN_DATA_BYTES_8;
  hfdcan1.Init.RxBuffersNbr = 0U;
  hfdcan1.Init.RxBufferSize = FDCAN_DATA_BYTES_8;
  hfdcan1.Init.TxEventsNbr = 0U;
  hfdcan1.Init.TxBuffersNbr = 0U;
  hfdcan1.Init.TxFifoQueueElmtsNbr = 8U;
  hfdcan1.Init.TxFifoQueueMode = FDCAN_TX_FIFO_OPERATION;
  hfdcan1.Init.TxElmtSize = FDCAN_DATA_BYTES_8;
  if (HAL_FDCAN_Init(&hfdcan1) != HAL_OK)
  {
    return 0U;
  }

  hfdcan2.Instance = FDCAN2;
  hfdcan2.Init = hfdcan1.Init;
  hfdcan2.Init.MessageRAMOffset = 854U;
  hfdcan2.Init.RxFifo0ElmtsNbr = 0U;
  hfdcan2.Init.RxFifo1ElmtsNbr = 16U;
  if (HAL_FDCAN_Init(&hfdcan2) != HAL_OK)
  {
    return 0U;
  }

  filter.IdType = FDCAN_STANDARD_ID;
  filter.FilterIndex = 0U;
  filter.FilterType = FDCAN_FILTER_MASK;
  filter.FilterConfig = FDCAN_FILTER_TO_RXFIFO0;
  filter.FilterID1 = 0U;
  filter.FilterID2 = 0U;
  if (HAL_FDCAN_ConfigFilter(&hfdcan1, &filter) != HAL_OK)
  {
    return 0U;
  }

  filter.FilterConfig = FDCAN_FILTER_TO_RXFIFO1;
  if (HAL_FDCAN_ConfigFilter(&hfdcan2, &filter) != HAL_OK)
  {
    return 0U;
  }

  if (HAL_FDCAN_ConfigGlobalFilter(&hfdcan1, FDCAN_REJECT, FDCAN_REJECT,
                                   FDCAN_FILTER_REMOTE, FDCAN_FILTER_REMOTE) != HAL_OK)
  {
    return 0U;
  }
  if (HAL_FDCAN_ConfigGlobalFilter(&hfdcan2, FDCAN_REJECT, FDCAN_REJECT,
                                   FDCAN_FILTER_REMOTE, FDCAN_FILTER_REMOTE) != HAL_OK)
  {
    return 0U;
  }

  if (HAL_FDCAN_ActivateNotification(&hfdcan1, FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0U) != HAL_OK)
  {
    return 0U;
  }
  if (HAL_FDCAN_ActivateNotification(&hfdcan2, FDCAN_IT_RX_FIFO1_NEW_MESSAGE, 0U) != HAL_OK)
  {
    return 0U;
  }

  HAL_NVIC_SetPriority(FDCAN1_IT0_IRQn, 3U, 0U);
  HAL_NVIC_EnableIRQ(FDCAN1_IT0_IRQn);
  HAL_NVIC_SetPriority(FDCAN2_IT0_IRQn, 3U, 0U);
  HAL_NVIC_EnableIRQ(FDCAN2_IT0_IRQn);

  if (HAL_FDCAN_Start(&hfdcan1) != HAL_OK)
  {
    return 0U;
  }
  if (HAL_FDCAN_Start(&hfdcan2) != HAL_OK)
  {
    return 0U;
  }

  return 1U;
}

void Bridge_Init(void)
{
  usb_rx_head = 0U;
  usb_rx_tail = 0U;
  usb_tx_head = 0U;
  usb_tx_tail = 0U;
  usb_tx_length = 0U;
  usb_tx_pending = 0U;
  usb_tx_busy = 0U;
  can_event_head = 0U;
  can_event_tail = 0U;
  protocol_length = 0U;
  can_streaming = 0U;
  tx_sequence = 0U;
  can_ready = CanInit();
}

void Bridge_UsbReceive(const uint8_t *data, uint32_t length)
{
  uint32_t i;
  uint16_t next;
  uint16_t head;
  uint16_t tail;

  if ((data == NULL) || (length == 0U))
  {
    return;
  }

  head = usb_rx_head;
  tail = usb_rx_tail;

  for (i = 0U; i < length; i++)
  {
    next = (uint16_t)((head + 1U) % USB_RX_RING_SIZE);
    if (next == tail)
    {
      break;
    }
    usb_rx_ring[head] = data[i];
    head = next;
  }

  usb_rx_head = head;
}

void Bridge_UsbTxComplete(void)
{
  usb_tx_busy = 0U;
}

void Bridge_Process(void)
{
  CanEvent event;
  uint8_t payload[CAN_PAYLOAD_SIZE];
  uint16_t next;

  while (usb_rx_tail != usb_rx_head)
  {
    ProtocolFeedByte(usb_rx_ring[usb_rx_tail]);
    usb_rx_tail = (uint16_t)((usb_rx_tail + 1U) % USB_RX_RING_SIZE);
  }

  while (can_event_tail != can_event_head)
  {
    event = can_event_queue[can_event_tail];
    next = (uint16_t)((can_event_tail + 1U) % CAN_EVENT_QUEUE_DEPTH);
    can_event_tail = next;

    if (can_streaming == 0U)
    {
      continue;
    }

    payload[0] = event.bus;
    payload[1] = (uint8_t)(event.id & 0xFFU);
    payload[2] = (uint8_t)((event.id >> 8) & 0xFFU);
    payload[3] = (uint8_t)((event.id >> 16) & 0xFFU);
    payload[4] = (uint8_t)((event.id >> 24) & 0xFFU);
    payload[5] = event.flags;
    payload[6] = event.length;
    memset(&payload[7], 0, 8U);
    if (event.length > 0U)
    {
      memcpy(&payload[7], event.data, event.length);
    }
    payload[15] = (uint8_t)(event.timestamp & 0xFFU);
    payload[16] = (uint8_t)((event.timestamp >> 8) & 0xFFU);
    payload[17] = (uint8_t)((event.timestamp >> 16) & 0xFFU);
    payload[18] = (uint8_t)((event.timestamp >> 24) & 0xFFU);

    (void)UsbQueueFrame(BRIDGE_CMD_CAN_RX, payload, CAN_PAYLOAD_SIZE,
                        tx_sequence++);
  }

  UsbTxPump();
}

void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef *hfdcan, uint32_t RxFifo0ITs)
{
  FDCAN_RxHeaderTypeDef header;
  uint8_t data[8];

  if (((RxFifo0ITs & FDCAN_IT_RX_FIFO0_NEW_MESSAGE) == 0U) ||
      (hfdcan->Instance != FDCAN1))
  {
    return;
  }

  while (HAL_FDCAN_GetRxFifoFillLevel(hfdcan, FDCAN_RX_FIFO0) > 0U)
  {
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO0, &header, data) == HAL_OK)
    {
      CanEventPush(0U, &header, data);
    }
  }
}

void HAL_FDCAN_RxFifo1Callback(FDCAN_HandleTypeDef *hfdcan, uint32_t RxFifo1ITs)
{
  FDCAN_RxHeaderTypeDef header;
  uint8_t data[8];

  if (((RxFifo1ITs & FDCAN_IT_RX_FIFO1_NEW_MESSAGE) == 0U) ||
      (hfdcan->Instance != FDCAN2))
  {
    return;
  }

  while (HAL_FDCAN_GetRxFifoFillLevel(hfdcan, FDCAN_RX_FIFO1) > 0U)
  {
    if (HAL_FDCAN_GetRxMessage(hfdcan, FDCAN_RX_FIFO1, &header, data) == HAL_OK)
    {
      CanEventPush(1U, &header, data);
    }
  }
}

void FDCAN1_IT0_IRQHandler(void)
{
  HAL_FDCAN_IRQHandler(&hfdcan1);
}

void FDCAN2_IT0_IRQHandler(void)
{
  HAL_FDCAN_IRQHandler(&hfdcan2);
}
